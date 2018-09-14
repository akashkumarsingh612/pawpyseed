# coding: utf-8

## @package pawpyseed.core.wavefunction
# Base class containing Python classes for parsing files
# and storing and analyzing wavefunction data.


from pymatgen.io.vasp.inputs import Potcar, Poscar
from pymatgen.io.vasp.outputs import Vasprun, Outcar
from pymatgen.core.structure import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
import numpy as np
from ctypes import *
from pawpyseed.core.utils import *
import os, time
import numpy as np
import json

import sys

class Timer:
	@staticmethod
	def setup_time(t):
		Timer.ALL_SETUP_TIME += t
	@staticmethod
	def overlap_time(t):
		Timer.ALL_OVERLAP_TIME += t
	@staticmethod
	def augmentation_time(t):
		Timer.ALL_AUGMENTATION_TIME += t
	ALL_SETUP_TIME = 0
	ALL_OVERLAP_TIME = 0
	ALL_AUGMENTATION_TIME = 0

class Pseudopotential:
	"""
	Contains important attributes from a VASP pseudopotential files. POTCAR
	"settings" can be read from the pymatgen POTCAR object

	Note: for the following attributes, 'index' refers to an energy
	quantum number epsilon and angular momentum quantum number l,
	which define one set consisting of a projector function, all electron
	partial waves, and pseudo partial waves.

	Attributes:
		rmaxstr (str): Maximum radius of the projection operators, as string
			of double precision float
		grid (np.array): radial grid on which partial waves are defined
		aepotential (np.array): All electron potential defined radially on grid
		aecorecharge (np.array): All electron core charge defined radially
			on grid (i.e. charge due to core, and not valence, electrons)
		kinetic (np.array): Core kinetic energy density, defined raidally on grid
		pspotential (np.array): pseudopotential defined on grid
		pscorecharge (np.array): pseudo core charge defined on grid
		ls (list): l quantum number for each index
		pswaves (list of np.array): pseudo partial waves for each index
		aewaves (list of np.array): all electron partial waves for each index
		projgrid (np.array): radial grid on which projector functions are defined
		recipprojs (list of np.array): reciprocal space projection operators
			for each index
		realprojs (list of np.array): real space projection operators
			for each index
	"""

	def __init__(self, data, rmax):
		nonradial, radial = data.split("PAW radial sets", 1)
		partial_waves = radial.split("pseudo wavefunction")
		gridstr, partial_waves = partial_waves[0], partial_waves[1:]
		self.rmax = rmax
		self.pswaves = []
		self.aewaves = []
		self.recipprojs = []
		self.realprojs = []
		self.nonlocalprojs = []
		self.ls = []
		self.rmaxstrs = []

		auguccstr, gridstr = gridstr.split("grid", 1)
		gridstr, aepotstr = gridstr.split("aepotential", 1)
		aepotstr, corechgstr = aepotstr.split("core charge-density", 1)
		try:
			corechgstr, kenstr = corechgstr.split("kinetic energy-density", 1)
			kenstr, pspotstr = kenstr.split("pspotential", 1)
		except:
			kenstr = "0 0"
			corechgstr, pspotstr = corechgstr.split("pspotential", 1)
		pspotstr, pscorechgstr = pspotstr.split("core charge-density (pseudized)", 1)
		self.grid = self.make_nums(gridstr)
		self.aepotential = self.make_nums(aepotstr)
		self.aecorecharge = self.make_nums(corechgstr)
		self.kinetic = self.make_nums(kenstr)
		self.pspotential = self.make_nums(pspotstr)
		self.pscorecharge = self.make_nums(pscorechgstr)

		augstr, uccstr = auguccstr.split('uccopancies in atom', 1)
		head, augstr = augstr.split('augmentation charges (non sperical)', 1)
		self.augs = self.make_nums(augstr)

		for pwave in partial_waves:
			lst = pwave.split("ae wavefunction", 1)
			self.pswaves.append(self.make_nums(lst[0]))
			self.aewaves.append(self.make_nums(lst[1]))

		projstrs = nonradial.split("Non local Part")
		topstr, projstrs = projstrs[0], projstrs[1:]
		self.T = float(topstr[-22:-4])
		topstr, atpschgstr = topstr[:-22].split("atomic pseudo charge-density", 1)
		try:
			topstr, corechgstr = topstr.split("core charge-density (partial)", 1)
			settingstr, localstr = topstr.split("local part", 1)
		except:
			corechgstr = "0 0"
			settingstr, localstr = topstr.split("local part", 1)
		localstr, self.gradxc = localstr.split("gradient corrections used for XC", 1)
		self.gradxc = int(self.gradxc)
		self.localpart = self.make_nums(localstr)
		self.localnum = self.localpart[0]
		self.localpart = self.localpart[1:]
		self.coredensity = self.make_nums(corechgstr)
		self.atomicdensity = self.make_nums(atpschgstr)

		for projstr in projstrs:
			lst = projstr.split("Reciprocal Space Part")
			nonlocalvals, projs = lst[0], lst[1:]
			self.rmaxstr = c_char_p()
			self.rmaxstr.value = nonlocalvals.split()[2].encode('utf-8')
			self.rmax = self.make_nums(nonlocalvals.split()[2])[0]
			nonlocalvals = self.make_nums(nonlocalvals)
			l = nonlocalvals[0]
			count = nonlocalvals[1]
			self.nonlocalprojs.append(nonlocalvals[2:])
			for proj in projs:
				recipproj, realproj = proj.split("Real Space Part")
				self.recipprojs.append(self.make_nums(recipproj))
				self.realprojs.append(self.make_nums(realproj))
				self.ls.append(l)

		settingstr, projgridstr = settingstr.split("STEP   =")
		self.ndata = int(settingstr.split()[-1])
		projgridstr = projgridstr.split("END")[0]
		self.projgrid = self.make_nums(projgridstr)
		self.step = (self.projgrid[0], self.projgrid[1])

		self.projgrid = np.linspace(0,rmax/1.88973,self.ndata,False,dtype=np.float64)

	def make_nums(self, numstring):
		return np.fromstring(numstring, dtype = np.float64, sep = ' ')

class CoreRegion:
	"""
	List of Pseudopotential objects to describe the core region of a structure.

	Attributes:
		pps (dict of Pseudopotential): keys are element symbols,
			values are Pseudopotential objects
	"""

	def __init__(self, potcar):
		self.pps = {}
		for potsingle in potcar:
			self.pps[potsingle.element] = Pseudopotential(potsingle.data[:-15], potsingle.rmax)
		

class PseudoWavefunction:
	"""
	Class for storing pseudowavefunction from WAVECAR file. Most important attribute
	is wf_ptr, a C pointer used in the C portion of the program for storing
	plane wave coefficients

	Attributes:
		kpts (np.array): nx3 array of fractional kpoint vectors,
			where n is the number of kpoints
		kws (np.array): weight of each kpoint
		wf_ptr (ctypes POINTER): c pointer to pswf_t object
	"""

	def __init__(self, filename="WAVECAR", vr="vasprun.xml"):
		if type(vr) == str:
			vr = Vasprun(vr)
		weights = vr.actual_kpoints_weights
		kws = numpy_to_cdouble(weights)
		self.kws = weights
		self.kpts = vr.actual_kpoints
		self.wf_ptr = PAWC.read_wavefunctions(filename.encode('utf-8'), kws)

	def pseudoprojection(self, band_num, basis):
		"""
		Computes <psibt_n1k|psit_n2k> for all n1 and k
		and a given n2, where psibt are basis structures
		pseudowavefunctions and psit are self pseudowavefunctions

		Arguments:
			band_num (int): n2 (see description)
			basis (Pseudowavefunction): pseudowavefunctions onto whose bands
				the band of self is projected
		"""
		nband = PAWC.get_nband(c_void_p(basis.wf_ptr))
		nwk = PAWC.get_nwk(c_void_p(basis.wf_ptr))
		nspin = PAWC.get_nspin(c_void_p(basis.wf_ptr))

		res = PAWC.pseudoprojection(c_void_p(basis.wf_ptr), c_void_p(self.wf_ptr), band_num)
		res = cdouble_to_numpy(res, 2*nband*nwk*nspin)
		return res[::2] + 1j * res[1::2]


class Wavefunction:
	"""
	Class for storing and manipulating all electron wave functions in the PAW
	formalism.

	Attributes:
		structure (pymatgen.core.structure.Structure): stucture of the material
			that the wave function describes
		pwf (PseudoWavefunction): Pseudowavefunction componenet
		cr (CoreRegion): Contains the pseudopotentials, with projectors and
			partials waves, for the structure
		projector: ctypes object for interfacing with C code
		wf_ptr (C pointer): pointer to the pswf_t C object for this wavefunction
		dim (np.ndarray, length 3): dimension of the FFT grid used by VASP
			and therefore for FFTs in this code
	"""

	def __init__(self, struct, pwf, cr, outcar, setup_projectors=True):
		"""
		Arguments:
			struct (pymatgen.core.Structure): structure that the wavefunction describes
			pwf (PseudoWavefunction): Pseudowavefunction componenet
			cr (CoreRegion): Contains the pseudopotentials, with projectors and
				partials waves, for the structure
			outcar (pymatgen.io.vasp.outputs.Outcar): Outcar object for reading ngf
		Returns:
			Wavefunction object
		"""
		self.structure = struct
		self.pwf = pwf
		self.cr = cr
		if type(outcar) == Outcar:
			self.dim = outcar.ngf
		else:
			#assume outcar is actually ngf, will fix later
			self.dim = outcar
		self.dim = np.array(self.dim).astype(np.int32) // 2
		self.projector_owner = False
		self.projector_list = None
		self.nums = None
		self.coords = None
		if setup_projectors:
			self.check_c_projectors()
		self.nband = PAWC.get_nband(c_void_p(pwf.wf_ptr))
		self.nwk = PAWC.get_nwk(c_void_p(pwf.wf_ptr))
		self.nspin = PAWC.get_nspin(c_void_p(pwf.wf_ptr))
		self.num_proj_els = None

	@staticmethod
	def from_files(struct="CONTCAR", pwf="WAVECAR", cr="POTCAR",
		vr="vasprun.xml", outcar="OUTCAR", setup_projectors=True):
		"""
		Construct a Wavefunction object from file paths.
		Arguments:
			struct (str): VASP POSCAR or CONTCAR file path
			pwf (str): VASP WAVECAR file path
			vr (str): VASP vasprun file path
		Returns:
			Wavefunction object
		"""
		return Wavefunction(Poscar.from_file(struct).structure,
			PseudoWavefunction(pwf, vr),
			CoreRegion(Potcar.from_file(cr)),
			Outcar(outcar), setup_projectors)

	@staticmethod
	def from_directory(path, setup_projectors=True):
		"""
		Assumes VASP output has the default filenames and is located
		in the directory specificed by path.
		"""
		filepaths = []
		for d in ["CONTCAR", "WAVECAR", "POTCAR", "vasprun.xml", "OUTCAR"]:
			filepaths.append(str(os.path.join(path, d)))
		args = filepaths + [setup_projectors]
		return Wavefunction.from_files(*args)

	def single_band_projection(self, band_num, basis):
		"""
		All electron projection of the band_num band of self
		onto all the bands of basis. Returned as a numpy array,
		with the overlap operator matrix elements ordered as follows:
		loop over band
			loop over spin
				loop over kpoint

		Arguments:
			band_num (int): band which is projected onto basis
			basis (Wavefunction): basis Wavefunction object

		Returns:
			res (np.array): overlap operator expectation values
				as described above
		"""

		return self.pwf.pseudoprojection(band_num, basis.pwf)

	def get_c_projectors_from_pps(self, pps):
		"""
		Returns a point to a list of ppot_t objects in C,
		to be used for high performance parts of the code

		Args:
			pps (dict of Pseudopotential objects): keys are integers,
				values of Pseudopotential objects

		Returns:
			c_void_p object pointing to ppot_t list with each Pseudopotential,
			ordered in the list by their numerical keys
		"""

		clabels = np.array([], np.int32)
		ls = np.array([], np.int32)
		projectors = np.array([], np.float64)
		aewaves = np.array([], np.float64)
		pswaves = np.array([], np.float64)
		wgrids = np.array([], np.float64)
		pgrids = np.array([], np.float64)
		augs = np.array([], np.float64)
		rmaxstrs = (c_char_p * len(pps))()
		rmaxs = np.array([], np.float64)
		num_els = 0

		for num in sorted(pps.keys()):
			print ("THIS IS THE NUM %d" % num)
			pp = pps[num]
			clabels = np.append(clabels, [num, len(pp.ls), pp.ndata, len(pp.grid)])
			rmaxstrs[num_els] = pp.rmaxstr
			rmaxs = np.append(rmaxs, pp.rmax)
			ls = np.append(ls, pp.ls)
			wgrids = np.append(wgrids, pp.grid)
			pgrids = np.append(pgrids, pp.projgrid)
			augs = np.append(augs, pp.augs)
			num_els += 1
			for i in range(len(pp.ls)):
				proj = pp.realprojs[i]
				aepw = pp.aewaves[i]
				pspw = pp.pswaves[i]
				projectors = np.append(projectors, proj)
				aewaves = np.append(aewaves, aepw)
				pswaves = np.append(pswaves, pspw)

		#print (num_els, clabels, ls, pgrids, wgrids, rmaxs)
		grid_encut = (2 * np.pi * self.dim / self.structure.lattice.abc)**2 / 0.262
		return cfunc_call(PAWC.get_projector_list, None,
							num_els, clabels, ls, pgrids, wgrids,
							projectors, aewaves, pswaves,
							rmaxs, max(grid_encut))
			

	def make_c_projectors(self, basis=None):
		"""
		Uses the CoreRegion objects in self and basis (if not None)
		to construct C representations of the projectors and partial waves
		for a structure. Also assigns numerical labels for each element and
		returns a list of indices and positions which can be easily converted
		to C lists for projection functions.

		Arguments:
			basis (None or Wavefunction): an additional structure from which
				to include pseudopotentials. E.g. can be useful if a basis contains
				some different elements than self.
		Returns:
			projector_list (C pointer): describes the pseudopotential data in C
			selfnums (int32 numpy array): numerical element label for each site in
				the structure
			selfcoords (float64 numpy array): flattened list of coordinates of each site
				in self
			basisnums (if basis != None): same as selfnums, but for basis
			basiscoords (if basis != None): same as selfcoords, but for basis
		"""
		pps = {}
		labels = {}
		label = 0
		for e in self.cr.pps:
			pps[label] = self.cr.pps[e]
			labels[e] = label
			label += 1
		#print (pps, labels)
		if basis != None:
			for e in basis.cr.pps:
				if not e in labels:
					pps[label] = basis.cr.pps[e]
					labels[e] = label
					label += 1
		
		projector_list = self.get_c_projectors_from_pps(pps)

		selfnums = np.array([labels[el(s)] for s in self.structure], dtype=np.int32)
		selfcoords = np.array([], np.float64)
		if basis != None:
			basisnums = np.array([labels[el(s)] for s in basis.structure], dtype=np.int32)
			basiscoords = np.array([], np.float64)

		self.num_proj_els = len(pps)
		if basis != None:
			basis.num_proj_els = len(pps)
		for s in self.structure:
			selfcoords = np.append(selfcoords, s.frac_coords)
		if basis != None:
			for s in basis.structure:
				basiscoords = np.append(basiscoords, s.frac_coords)
			return projector_list, selfnums, selfcoords, basisnums, basiscoords
		return projector_list, selfnums, selfcoords

	def proportion_conduction(self, band_num, bulk, spinpol = False):
		"""
		Calculates the proportion of band band_num in self
		that projects onto the valence states and conduction
		states of bulk. Designed for analysis of point defect
		wavefunctions.

		Arguments:
			band_num (int): number of defect band in self
			bulk (Wavefunction): wavefunction of bulk crystal
				with the same lattice and basis set as self

		Returns:
			v, c (int, int): The valence (v) and conduction (c)
				proportion of band band_num
		"""

		nband = PAWC.get_nband(c_void_p(bulk.pwf.wf_ptr))
		nwk = PAWC.get_nwk(c_void_p(bulk.pwf.wf_ptr))
		nspin = PAWC.get_nspin(c_void_p(bulk.pwf.wf_ptr))
		occs = cdouble_to_numpy(PAWC.get_occs(c_void_p(bulk.pwf.wf_ptr)), nband*nwk*nspin)

		res = self.pwf.pseudoprojection(band_num, bulk.pwf)

		if spinpol:
			c, v = np.zeros(nspin), np.zeros(nspin)
			for b in range(nband):
				for s in range(nspin):
					for k in range(nwk):
						i = b*nspin*nwk + s*nwk + k
						if occs[i] > 0.5:
							v[s] += np.absolute(res[i]) ** 2 * self.pwf.kws[i%nwk]
						else:
							c[s] += np.absolute(res[i]) ** 2 * self.pwf.kws[i%nwk]
		else:
			c, v = 0, 0
			for i in range(nband*nwk*nspin):
				if occs[i] > 0.5:
					v += np.absolute(res[i]) ** 2 * self.pwf.kws[i%nwk] / nspin
				else:
					c += np.absolute(res[i]) ** 2 * self.pwf.kws[i%nwk] / nspin
		t = v+c
		v /= t
		c /= t
		if spinpol:
			v = v.tolist()
			c = c.tolist()
		return v, c

	def defect_band_analysis(self, bulk, num_below_ef=20, num_above_ef=20, spinpol = False):
		"""
		Identifies a set of 'interesting' bands in a defect structure
		to analyze by choosing any band that is more than bound conduction
		and more than bound valence in the pseudoprojection scheme,
		and then fully analyzing these bands using single_band_projection

		Args:
			bulk (Wavefunction object): bulk structure wavefunction
			num_below_ef (int, 20): number of bands to analyze below the fermi level
			num_above_ef (int, 20): number of bands to analyze above the fermi level
			spinpol (bool, False): whether to return spin-polarized results (only allowed
				for spin-polarized DFT output)
		"""
		nband = PAWC.get_nband(c_void_p(bulk.pwf.wf_ptr))
		nwk = PAWC.get_nwk(c_void_p(bulk.pwf.wf_ptr))
		nspin = PAWC.get_nspin(c_void_p(bulk.pwf.wf_ptr))
		
		occs = cdouble_to_numpy(PAWC.get_occs(c_void_p(bulk.pwf.wf_ptr)), nband*nwk*nspin)
		vbm = 0
		for i in range(nband):
			if occs[i*nwk*nspin] > 0.5:
				vbm = i
		min_band, max_band = vbm - num_below_ef, vbm + num_above_ef
		if min_band < 0 or max_band >= nband:
			raise PAWpyError("The min or max band is too large/small with min_band=%d, max_band=%d, nband=%d" % (min_band, max_band, nband))

		totest = [i for i in range(min_band,max_band+1)]
		print("NUM TO TEST", len(totest))

		results = {}
		for b in totest:
			results[b] = self.proportion_conduction(b, bulk, spinpol = spinpol)

		return results

	def check_c_projectors(self):
		"""
		Check to see if the projector functions have been read in and set up.
		If not, do so.
		"""
		if not self.projector_list:
			self.projector_owner = True
			self.projector_list, self.nums, self.coords = self.make_c_projectors()
			cfunc_call(PAWC.setup_projections_no_rayleigh, None,
					self.pwf.wf_ptr, self.projector_list,
					self.num_proj_els, len(self.structure), self.dim,
					self.nums, self.coords)

	def get_state_realspace(self, b, k, s, dim=None):
		"""
		Returns the real and imaginary parts of a given band.
		Args:
			b (int): band number
			k (int): kpoint number
			s (int): spin number
			dim (numpy array of 3 ints): dimensions of the FFT grid
		Returns:
			An array (x slow-indexed) where the first half of the values
				are the real part and second half of the values are the
				imaginary part
		"""

		self.check_c_projectors()
		if type(dim) == type(None):
			dim = self.dim
		return cfunc_call(PAWC.realspace_state_ri, 2*dim[0]*dim[1]*dim[2], b, k+s*self.nwk,
			self.pwf.wf_ptr, self.projector_list,
			dim, self.nums, self.coords)

	def _convert_to_vasp_volumetric(self, filename, dim):
		

		#from pymatgen VolumetricData class
		p = Poscar(self.structure)
		lines = filename + '\n'
		lines += "   1.00000000000000\n"
		latt = self.structure.lattice.matrix
		lines += " %12.6f%12.6f%12.6f\n" % tuple(latt[0, :])
		lines += " %12.6f%12.6f%12.6f\n" % tuple(latt[1, :])
		lines += " %12.6f%12.6f%12.6f\n" % tuple(latt[2, :])
		lines += "".join(["%5s" % s for s in p.site_symbols]) + "\n"
		lines += "".join(["%6d" % x for x in p.natoms]) + "\n"
		lines += "Direct\n"
		for site in self.structure:
			lines += "%10.6f%10.6f%10.6f\n" % tuple(site.frac_coords)
		lines += " \n"
	
		f = open(filename, 'r')
		nums = f.read()
		f.close()
		f = open(filename, 'w')
		dimstr = '%d %d %d\n' % (dim[0], dim[1], dim[2])
		#pos = Poscar(self.structure, velocities = None)
		#posstr = pos.get_string() + '\n'
		f.write(lines + dimstr + nums)
		f.close()

	def write_state_realspace(self, b, k, s, fileprefix = "", dim=None, return_wf = False):
		"""
		Writes the real and imaginary parts of a given band to two files,
		prefixed by fileprefix

		Args:
			b (int): band number (0-indexed!)
			k (int): kpoint number (0-indexed!)
			s (int): spin number (0-indexed!)
			dim (numpy array of 3 ints): dimensions of the FFT grid
			fileprefix (string, optional): first part of the file name
			return_wf (bool): whether to return the wavefunction
		Returns:
			(if return_wf==True) An array (x slow-indexed) where the first half of the values
				are the real part and second half of the values are the
				imaginary part
			The wavefunction is written with z the slow index.
		"""
		res = None
		print("PARAMETERS", self.nums, self.coords, dim)
		sys.stdout.flush()
		self.check_c_projectors()
		if type(dim) == type(None):
			dim = self.dim
		filename_base = "%sB%dK%dS%d" % (fileprefix, b, k, s)
		filename1 = "%s_REAL" % filename_base
		filename2 = "%s_IMAG" % filename_base
		print("PARAMETERS", self.nums, self.coords, dim)
		sys.stdout.flush()
		if return_wf:
			res = cfunc_call(PAWC.write_realspace_state_ri_return, 2*dim[0]*dim[1]*dim[2],
				filename1, filename2,
				b, k+s*self.nwk,
				self.pwf.wf_ptr, self.projector_list,
				dim, self.nums, self.coords)
		else:
			cfunc_call(PAWC.write_realspace_state_ri_noreturn, None, filename1, filename2,
				b, k+s*self.nwk,
				self.pwf.wf_ptr, self.projector_list,
				dim, self.nums, self.coords)
		self._convert_to_vasp_volumetric(filename1, dim)
		self._convert_to_vasp_volumetric(filename2, dim)
		return res

	def write_density_realspace(self, filename = "PYAECCAR", dim=None, return_wf = False):
		"""
		Writes the AE charge density to a file. Returns it if desired.

		Args:
			b (int): band number
			k (int): kpoint number
			s (int): spin number
			dim (numpy array of 3 ints): dimensions of the FFT grid
			filename (string, "PYAECCAR"): charge density filename
			return_wf (bool): whether to return the wavefunction
		Returns:
			(if return_wf==True) An array (x slow-indexed, as in VASP)
				with the charge densities
			The charge density is written with z the slow index.
		"""

		res = None
		self.check_c_projectors()
		if type(dim) == type(None):
			dim = self.dim
		if return_wf:
			res = cfunc_call(PAWC.write_density_return, dim[0]*dim[1]*dim[2], filename,
				self.pwf.wf_ptr, self.projector_list, dim, self.nums, self.coords)
		else:
			cfunc_call(PAWC.write_density_noreturn, None, filename,
				self.pwf.wf_ptr, self.projector_list, dim, self.nums, self.coords)
			res = None
		self._convert_to_vasp_volumetric(filename, dim)
		return res

	def get_nosym_kpoints(self, symprec=1e-3):
		kpts = np.array(self.pwf.kpts)
		allkpts = []
		orig_kptnums = []
		op_nums = []
		sga = SpacegroupAnalyzer(self.structure, symprec)
		symmops = sga.get_symmetry_operations()
		for k, kpt in enumerate(kpts):
			for i, op in enumerate(symmops):
				newkpt = op.operate(kpt)
				unique = True
				for nkpt in allkpts:
					if np.linalg.norm(newkpt-nkpt) < 1e-10 \
							and (np.abs(newkpt) < 1).all():
						unique = False
						break
				if unique:
					allkpts.append(newkpt)
					orig_kptnums.append(k)
					op_nums.append(i)
		self.nosym_kpts = allkpts
		self.orig_kptnums = orig_kptnums
		self.op_nums = op_nums
		self.symmops = symmops
		return allkpts, orig_kptnums, op_nums, symmops

	def get_kpt_mapping(self, allkpts, symprec=1e-3):
		sga = SpacegroupAnalyzer(self.structure, symprec)
		symmops = sga.get_symmetry_operations()
		kpts = np.array(self.pwf.kpts)
		orig_kptnums = []
		op_nums = []
		for nkpt in allkpts:
			match = False
			for k, kpt in enumerate(kpts):
				for i, op in enumerate(symmops):
					newkpt = op.operate(kpt)
					if np.linalg.norm(newkpt-nkpt) < 1e-10:
						match = True
						orig_kptnums.append(k)
						op_nums.append(i)
						break
				if match:
					break
			if not match:
				raise PAWpyError("Could not find kpoint mapping")
		return orig_kptnums, op_nums, symmops



	def free_all(self):
		"""
		Frees all of the C structures associated with the Wavefunction object.
		After being called, this object is not usable.
		"""
		PAWC.free_pswf(c_void_p(self.pwf.wf_ptr))
		if self.projector_owner:
			PAWC.free_ppot_list(c_void_p(self.projector_list), len(self.cr.pps))

