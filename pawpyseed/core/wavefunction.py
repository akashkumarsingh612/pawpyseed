# coding: utf-8

## @package pawpyseed.core.wavefunction
# Base class containing Python classes for parsing files
# and storing and analyzing wavefunction data.

from pymatgen.io.vasp.inputs import Potcar, Poscar
from pymatgen.io.vasp.outputs import Vasprun, Outcar
from pymatgen.core.structure import Structure
import numpy as np
from ctypes import *
from pawpyseed.core.utils import *
import pawpyseed.core.symmetry as pawpy_symm
import os, time
import numpy as np
import json

import sys

import pawpy

class Pseudopotential:
	"""
	Contains important attributes from a VASP pseudopotential files. POTCAR
	"settings" can be read from the pymatgen POTCAR object

	Note: for the following attributes, 'index' refers to an energy
	quantum number epsilon and angular momentum quantum number l,
	which define one set consisting of a projector function, all electron
	partial waves, and pseudo partial waves.

	Attributes:
		rmax (np.float64): Maximum radius of the projection operators
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


class Wavefunction(pawpy.CWavefunction):
	"""
	Class for storing and manipulating all electron wave functions in the PAW
	formalism.

	Attributes:
		structure (pymatgen.core.structure.Structure): stucture of the material
			that the wave function describes
		pwf (PseudoWavefunction): Pseudowavefunction componenet
		cr (CoreRegion): Contains the pseudopotentials, with projectors and
			partials waves, for the structure
		dim (np.ndarray, length 3): dimension of the FFT grid used by VASP
			and therefore for FFTs in this code
		nband, nwk, nspin (int): Number of bands, kpoints, spins in VASP calculation
		encut (int or float): VASP calculation plane-wave energy cutoff
		nums (list of int, length nsites): Element labels for the structure
		coords (list of float, length 3*nsites): Flattened list of coordinates for the structure
			data has been initialized for this structure
		projector_list (pointer): List of projector function/partial wave data
			for this structure
	"""

	def __init__(self, struct, pwf, cr, outcar, setup_projectors=False):
		"""
		Arguments:
			struct (pymatgen.core.Structure): structure that the wavefunction describes
			pwf (pawpy.PWFPointer): holder class for pswf_t and k-points/k-point weights
			cr (CoreRegion): Contains the pseudopotentials, with projectors and
				partials waves, for the structure
			outcar (pymatgen.io.vasp.outputs.Outcar): Outcar object for reading ngf
			setup_projectors (bool, False): Whether to set up the core region
				components of the wavefunctions (leave as False if passing this
				object to Projector, which will do the setup automatically)
		Returns:
			Wavefunction object
		"""
		self.band_props = pwf.band_props.copy(order = 'C')
		super(Wavefunction, self).__init__(pwf)
		if self.ncl:
			raise PAWpyError("Pseudowavefunction is noncollinear! Call NCLWavefunction(...) instead")
		self.structure = struct
		self.cr = cr
		if type(outcar) == Outcar:
			self.dim = outcar.ngf
			self.dim = np.array(self.dim).astype(np.int32) // 2
		else:
			#assume outcar is actually ngf, will fix later
			self.dim = outcar
			self.dim = np.array(self.dim).astype(np.int32)
		if setup_projectors:
			self.check_c_projectors()

	def desymmetrized_copy(self, allkpts = None, weights = None):
		if (not allkpts) or (not weights):
			pwf, allkpts, weights = self._desymmetrized_pwf(self.structure)
			new_wf = Wavefunction(self.structure, pwf, self.cr, self.dim)
			return new_wf, allkpts, weights
		else:
			pwf = self._desymmetrized_pwf(self.structure, allkpts, weights)
			new_wf = Wavefunction(self.structure, pwf, self.cr, self.dim)
			return new_wf

	@staticmethod
	def from_files(struct="CONTCAR", wavecar="WAVECAR", cr="POTCAR",
		vr="vasprun.xml", outcar="OUTCAR", setup_projectors=False):
		"""
		Construct a Wavefunction object from file paths.

		Arguments:
			struct (str): VASP POSCAR or CONTCAR file path
			pwf (str): VASP WAVECAR file path
			cr (str): VASP POTCAR file path
			vr (str): VASP vasprun file path
			outcar (str): VASP OUTCAR file path

		Returns:
			Wavefunction object
		"""
		pwf = pawpy.PWFPointer(wavecar, vr)
		return Wavefunction(Poscar.from_file(struct).structure,
			pwf, CoreRegion(Potcar.from_file(cr)),
			Outcar(outcar), setup_projectors)

	@staticmethod
	def from_directory(path, setup_projectors = False):
		"""
		Assumes VASP output has the default filenames and is located
		in the directory specificed by path.

		Arguments:
			path (str): VASP output directory
			setup_projectors (bool, False): Whether to set up the core region
				components of the wavefunctions (leave as False if passing this
				object to Projector, which will do the setup automatically)

		Returns:
			Wavefunction object
		"""
		filepaths = []
		for d in ["CONTCAR", "WAVECAR", "POTCAR", "vasprun.xml", "OUTCAR"]:
			filepaths.append(str(os.path.join(path, d)))
		args = filepaths + [setup_projectors]
		return Wavefunction.from_files(*args)

	@staticmethod
	def from_atomate_directory(path, setup_projectors = False):
		"""
		Assumes VASP output has the default filenames and is located
		in the directory specificed by path. Checks for
		gzipped files created by atomate

		Arguments:
			path (str): VASP output directory
			setup_projectors (bool, False): Whether to set up the core region
				components of the wavefunctions (leave as False if passing this
				object to Projector, which will do the setup automatically)

		Returns:
			Wavefunction object
		"""

		files = ["CONTCAR", "WAVECAR", "POTCAR", "vasprun.xml", "OUTCAR"]
		paths = []

		for file in files:
		    filepat = os.path.join( path, file +'.relax2.gz')
		    if not os.path.exists( filepat):
		        filepat = os.path.join( path, file +'.relax1.gz')
		    if not os.path.exists( filepat):
		        filepat = os.path.join( path, file +'.gz')
		    if not os.path.exists( filepat):
		        filepat = os.path.join( path, file)
		    if not os.path.exists( filepat):
		        print('Could not find {}! Skipping this defect...'.format(file))
		        return False

		    paths.append(filepat)

		args = paths + [setup_projectors]
		wf = Wavefunction.from_files(*args)

		return wf

	def _make_c_projectors(self):
		"""
		Uses the CoreRegion objects in self
		to construct C representations of the projectors and partial waves
		for a structure. Also assigns numerical labels for each element and
		setups up a list of indices and positions which can be easily converted
		to C lists for projection routines.
		"""

		pps = {}
		labels = {}
		label = 0
		for e in self.cr.pps:
			pps[label] = self.cr.pps[e]
			labels[e] = label
			label += 1

		nums = np.array([labels[el(s)] for s in self.structure], dtype=np.int32)
		coords = np.array([], dtype = np.float64)

		self.num_sites = len(self.structure)
		self.num_elems = len(pps)
		for s in self.structure:
			coords = np.append(coords, s.frac_coords)

		grid_encut = (np.pi * self.dim / self.structure.lattice.abc)**2 / 0.262

		self._c_projector_setup(self.num_elems, self.num_sites, max(grid_encut),
								nums, coords, self.dim, pps)

	def check_c_projectors(self):
		"""
		Check to see if the projector functions have been read in and set up.
		If not, do so.
		"""
		if not self.projector_owner:
			start = time.monotonic()
			self._make_c_projectors()
			end = time.monotonic()
			print('--------------\nran setup_projections in %f seconds\n---------------' % (end-start))

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
		if dim != None:
			self.update_dimv(np.array(dim))
		return self._get_realspace_state(b, k, s)

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

	def write_state_realspace(self, b, k, s, fileprefix = "", dim=None, scale = 1):
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
		self.check_c_projectors()
		if dim is not None:
			self.update_dimv(np.array(dim))
		filename_base = "%sB%dK%dS%d" % (fileprefix, b, k, s)
		filename1 = "%s_REAL" % filename_base
		filename2 = "%s_IMAG" % filename_base
		res = self._write_realspace_state(filename1, filename2, scale, b, k, s)
		self._convert_to_vasp_volumetric(filename1, dim)
		self._convert_to_vasp_volumetric(filename2, dim)
		return res

	def get_realspace_density(self, dim = None):
		self.check_c_projectors()
		if dim is not None:
			self.update_dimv(np.array(dim))
		return self._get_realspace_density()

	def write_density_realspace(self, filename = "PYAECCAR", dim=None, scale = 1):
		"""
		Writes the AE charge density to a file and returns it.

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

		self.check_c_projectors()
		if dim is not None:
			self.update_dimv(np.array(dim))
		res = self._write_realspace_density(filename, scale)
		self._convert_to_vasp_volumetric(filename, dim)
		return res

	def get_nosym_kpoints(self, init_kpts = None, symprec=1e-5,
		gen_trsym = True, fil_trsym = True):

		return pawpy_symm.get_nosym_kpoints(kpts, self.structure, init_kpts,
										symprec, gen_trsym, fil_trsym)

	def get_kpt_mapping(self, allkpts, symprec=1e-5, gen_trsym = True):

		return pawpy_symm.get_kpt_mapping(allkpts, self.kpts, self.structure,
										symprec, gen_trsym)
