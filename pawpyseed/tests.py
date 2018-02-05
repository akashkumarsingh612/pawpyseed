import unittest
import os, subprocess
import time

import numpy as np
from numpy.testing import assert_almost_equal

from scipy.special import lpmn, sph_harm

from pymatgen.io.vasp.inputs import Poscar, Potcar
from pymatgen.io.vasp.outputs import Vasprun
from pymatgen.core.structure import Structure

from wavefunction import *

from ctypes import *

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PAWC = CDLL(os.path.join(MODULE_DIR, "pawpy.so"))
PAWC.legendre.restype = c_double
PAWC.Ylmr.restype = c_double
PAWC.Ylmi.restype = c_double
PAWC.spline_coeff.restype = POINTER(POINTER(c_double))
PAWC.proj_interpolate.restype = c_double
PAWC.spherical_bessel_transform_setup.restype = POINTER(None)

def cdouble_to_numpy(arr, length):
	arr = cast(arr, POINTER(c_double))
	newarr = np.zeros(length)
	for i in range(length):
		newarr[i] = arr[i]
	#PAWC.free_ptr(arr)
	return newarr

def cfloat_to_numpy(arr, length):
	arr = cast(arr, POINTER(c_float))
	newarr = np.zeros(length)
	for i in range(length):
		newarr[i] = arr[i]
	#PAWC.free_ptr(arr)
	return newarr

def cfloat_to_numpy(arr, length):
	arr = cast(arr, POINTER(c_int))
	newarr = np.zeros(length)
	for i in range(length):
		newarr[i] = arr[i]
	#PAWC.free_ptr(arr)
	return newarr

def numpy_to_cdouble(arr):
	newarr = (c_double * len(arr))()
	for i in range(len(arr)):
		newarr[i] = arr[i]
	return newarr

def numpy_to_cfloat(arr):
	newarr = (c_float * len(arr))()
	for i in range(len(arr)):
		newarr[i] = arr[i]
	return newarr

def numpy_to_cint(arr):
	newarr = (c_int * len(arr))()
	for i in range(len(arr)):
		newarr[i] = int(arr[i])
	return newarr

class TestC:

	def setup(self):
		structure = Poscar.from_file("CONTCAR").structure
		cr = CoreRegion(Potcar.from_file("POTCAR"))
		pps = {}
		labels = {}
		label = 0
		for e in cr.pps:
			pps[label] = cr.pps[e]
			labels[e] = label
			label += 1
		clabels = np.array([], np.int32)
		ls = np.array([], np.int32)
		projectors = np.array([], np.float64)
		aewaves = np.array([], np.float64)
		pswaves = np.array([], np.float64)
		wgrids = np.array([], np.float64)
		pgrids = np.array([], np.float64)
		num_els = 0

		for num in pps:
			pp = pps[num]
			clabels = np.append(clabels, [num, len(pp.ls), pp.ndata, len(pp.grid)])
			ls = np.append(ls, pp.ls)
			wgrids = np.append(wgrids, pp.grid)
			pgrids = np.append(pgrids, pp.projgrid)
			num_els += 1
			for i in range(len(pp.ls)):
				proj = pp.realprojs[i]
				aepw = pp.aewaves[i]
				pspw = pp.pswaves[i]
				projectors = np.append(projectors, proj)
				aewaves = np.append(aewaves, aepw)
				pswaves = np.append(pswaves, pspw)
		print ("rmax", cr.pps['Ga'].rmax * 0.529177)

		selfnums = np.array([labels[el(s)] for s in structure], dtype=np.int32)
		selfcoords = np.array([], np.float64)

		for s in structure:
			selfcoords = np.append(selfcoords, s.frac_coords)

		f = open('potholder.txt', 'w')
		f.write('%d '%num_els)
		for i in range(len(clabels)):
			f.write('%d '%clabels[i])
		f.write('%d '%len(ls))
		for i in range(len(ls)):
			f.write('%d '%ls[i])
		f.write('%d '%len(pgrids))
		for i in range(len(pgrids)):
			f.write('%f '%pgrids[i])
		f.write('%d '%len(wgrids))
		for i in range(len(wgrids)):
			f.write('%f '%wgrids[i])
		f.write('%d '%len(projectors))
		for i in range(len(projectors)):
			f.write('%f '%projectors[i])
		f.write('%d '%len(aewaves))
		for i in range(len(aewaves)):
			f.write('%f '%aewaves[i])
		f.write('%d '%len(pswaves))
		for i in range(len(pswaves)):
			f.write('%f '%pswaves[i])
		f.write('%f '%(cr.pps['Ga'].rmax*0.529177))
		f.write('%d '%len(selfnums))
		for i in range(len(selfnums)):
			f.write('%d '%selfnums[i])
		for i in range(len(selfnums)*3):
			f.write('%f '%selfcoords[i])

		f.close()

	def teardown(self):
		pass

	def test_fac(self):
		assert PAWC.fac(5) == 120

	def test_legendre(self):
		xs = np.linspace(0,1,10000)
		ys = np.zeros(10000*16)
		ys2 = np.zeros(10000*16)
		t1 = time.time()
		for i in range(xs.shape[0]):
			if i == 0: print (lpmn(-3,3,xs[i])[0])
			ys[16*i:16*(i+1)] = lpmn(-3,3,xs[i])[0].flatten()
		t2 = time.time()
		for i in range(xs.shape[0]):
			for l in range(4):
				for m in range(0,-l-1,-1):
					if i == 0: print(PAWC.legendre(l, m, c_double(xs[i])))
					ys2[i*16-m*4+l] = PAWC.legendre(l, m, c_double(xs[i]))
		t3 = time.time()
		#rough speed check
		#assert 2*(t2-t1) > t3 - t2
		#accuracy check
		assert_almost_equal(np.linalg.norm(ys-ys2), 0.0)

	def test_Ylm(self):
		for l in range(4):
			for m in range(-l,1):
				xs = np.linspace(0,1,100)
				ys = np.zeros(10000, np.complex128)
				ys2 = np.zeros(10000, np.complex128)
				t1 = time.time()
				for i in range(xs.shape[0]):
					for j in range(xs.shape[0]):
						ys[i*100+j] = sph_harm(m, l, xs[j]*2*np.pi, xs[i]*np.pi)
				t2 = time.time()
				i,j=0,0
				for i in range(xs.shape[0]):
					for j in range(xs.shape[0]):
						ys2[i*100+j] = PAWC.Ylmr(l, m, c_double(xs[i]*np.pi), c_double(xs[j]*np.pi*2))\
										+ 1.0j*PAWC.Ylmi(l, m, c_double(xs[i]*np.pi), c_double(xs[j]*np.pi*2))
				t3 = time.time()
				#rough speed check
				assert 2*(t2-t1) > t3 - t2
				assert_almost_equal(np.linalg.norm(ys-ys2),0.0)

	def test_unit_conversion(self):
		struct = Poscar.from_file("CONTCAR").structure
		lattice = numpy_to_cdouble(struct.lattice.matrix.flatten())
		reclattice = numpy_to_cdouble(struct.lattice.reciprocal_lattice.matrix.flatten())
		for site in struct:
			coord = site.coords
			fcoord = site.frac_coords
			ccoord = numpy_to_cdouble(coord)
			cfcoord = numpy_to_cdouble(fcoord)
			print("check")
			PAWC.frac_to_cartesian(cfcoord, lattice)
			temp1 = cdouble_to_numpy(cfcoord, 3)
			assert_almost_equal(np.linalg.norm(temp1-coord), 0.0)
			print(temp1)
			PAWC.cartesian_to_frac(ccoord, reclattice)
			temp2 = cdouble_to_numpy(ccoord, 3)
			assert_almost_equal(np.linalg.norm(temp2-fcoord), 0.0)
			print(temp2)

	def test_spline(self):
		vr = Vasprun("vasprun.xml")
		cr = CoreRegion(Potcar.from_file("POTCAR"))
		struct = Poscar.from_file("POSCAR").structure
		grid = cr[0].projgrid
		vals = cr[0].realprojs[0]
		rmax = cr[0].rmax
		tst = np.linspace(0, max(grid), 400)
		res1 = scipy.interpolate.CubicSpline(grid, vals, extrapolate=True)(tst)
		x, y = numpy_to_cdouble(grid), numpy_to_cdouble(vals)
		cof = PAWC.spline_coeff(x, y, 100)
		res2 = (c_double * tst.shape[0])()
		for i in range(tst.shape[0]):
			res2[i] = PAWC.proj_interpolate(c_double(tst[i]), c_double(rmax), x, y, cof)
		res2 = cdouble_to_numpy(res2)
		print (res1-res2)


	def test_fft3d(self):
		vr = Vasprun("vasprun.xml")
		weights = vr.actual_kpoints_weights
		kws = (c_double * len(weights))()
		for i in range(len(weights)):
			kws[i] = weights[i]
		PAWC.fft_check("WAVECAR", kws, numpy_to_cint(np.array([40,40,40])))

	def test_sbt(self):
		import scipy.special.spherical_jn as jn
		k = 4
		cr = CoreRegion(Potcar.from_file("POTCAR"))
		r = cr.pps['Ga'].wavegrid
		f = cr.pps['Ga'].aewaves[2] - cr.pps['Ga'].aewaves[2];
		ks = (c_double * len(r))()
		sbtd = PAWC.spherical_bessel_transform_setup(520, 520, 2, 323, r)
		res = wave_spherical_bessel_transform(sbtd, numpy_to_cdouble(r),
			numpy_to_cdouble(f), ks, 1)
		vals = jn(1, r * k) * f
		integral = np.trapz(vals, r)
		print(ks)
		print (integral)

	def test_memory(self):
		f = open('mtest.out', 'w')
		subprocess.call('valgrind ./memtest'.split(), stdout=f, stderr=f)
		f.close()

class TestMem:

	def setup(self):
		pass

	def teardown(self):
		pass

	def test_read(self):
		f = open('readtest.out', 'w')
		subprocess.call('valgrind ./memtest read'.split(), stdout=f, stderr=f)
		f.close()

	def test_pseudo(self):
		f = open('pseudotest.out', 'w')
		subprocess.call('valgrind ./memtest pseudo'.split(), stdout=f, stderr=f)
		f.close()

	def test_list(self):
		f = open('listtest.out', 'w')
		subprocess.call('valgrind ./memtest list'.split(), stdout=f, stderr=f)
		f.close()

class TestPy:

	def setup():
		pass

	def teardown():
		pass

t = TestC()
t.setup()
t.test_legendre()
t.test_Ylm()
t.test_unit_conversion()
t.test_fft3d()
t.test_memory()

#t = TestMem()
#t.test_read()
#t.test_pseudo()
#t.test_list()
