# coding: utf-8

## @package pawpyseed.core.projector
# Defines the Projector class, an extension
# of the Wavefunction class for evaluating
# AE projection operators.

from pawpyseed.core.wavefunction import *

OPSIZE = 9

def make_c_ops(op_nums, symmops):
	print(op_nums)
	ops = np.zeros(OPSIZE*len(op_nums))
	for i in range(len(op_nums)):
		ops[OPSIZE*i:OPSIZE*(i+1)] = symmops[op_nums[i]].rotation_matrix.flatten()
	drs = np.zeros(3*len(op_nums))
	for i in range(len(op_nums)):
		drs[3*i:3*(i+1)] = symmops[op_nums[i]].translation_vector
	return ops, drs

class CopyPseudoWavefunction(PseudoWavefunction):
	def __init__(self, wf_ptr, kpts, kws):
		self.wf_ptr = wf_ptr
		self.kpts = kpts
		self.kws = kws

def copy_wf(rwf, wf_ptr, allkpts, weights, setup_projectors = True, free_ref = False):
	pwf = CopyPseudoWavefunction(wf_ptr, allkpts, weights)
	wf = Wavefunction(rwf.structure, pwf, rwf.cr, rwf.dim,
		setup_projectors)
	if free_ref:
		rwf.free_all()
	return wf

class Projector(Wavefunction):

	def __init__(self, wf, basis, projector_list = None,
		unsym_basis = False, unsym_wf = False, pseudo = False):
		"""
		Projector is a class to projector KS states
		from wf onto the KS states of basis
		(both wavefunction objects). Projector extends
		Wavefunction, so a Projector is essentially
		a Wavefunction object that is set up to be
		projected onto basis.

		Arguments:
			wf (Wavefunction): The wavefunction objects whose
				bands are to be projected onto basis
			basis (Wavefunction): The wavefunction whose bands
				serve as the basis set for projection
			projector_list (c_void_p) (default None): pointer to a list of C
				ppot_t objects. When manually calling the initializer,
				this should generally be left as the default, in which
				case the setup will be performed for wf and basis.
				projector_list != None is used by setup_multiple_projections
				for efficiency and memory management
			allkpts (2D numpy array) (default None): List of fractional
				coordinate k-points to map onto

		Returns:
			Projector object, containing all the same fields as
				wf but set up for projections onto basis
		"""
		#__init__(self, struct, pwf, cr, outcar, setup_projectors=True)
		#__init__(self, filename="WAVECAR", vr="vasprun.xml")

		if unsym_basis and unsym_wf:
			allkpts, borig_kptnums, bop_nums, bsymmops, btrs = basis.get_nosym_kpoints()
			weights = np.ones(allkpts.shape[0]) / allkpts.shape[0]
			worig_kptnums, wop_nums, wsymmops, wtrs = wf.get_kpt_mapping(allkpts)
			bops, bdrs = make_c_ops(bop_nums, bsymmops)
			wops, wdrs = make_c_ops(wop_nums, wsymmops)
			bptr = cfunc_call(PAWC.expand_symm_wf, None, basis.pwf.wf_ptr,
				len(borig_kptnums), borig_kptnums, bops, bdrs, weights, btrs)
			wptr = cfunc_call(PAWC.expand_symm_wf, None, wf.pwf.wf_ptr,
				len(worig_kptnums), worig_kptnums, wops, wdrs, weights, wtrs)
			basis = copy_wf(basis, bptr, allkpts, weights, False, True)
			wf = copy_wf(wf, wptr, allkpts, weights, False, True)
		elif unsym_wf and not unsym_basis:
			allkpts = basis.pwf.kpts
			weights = basis.pwf.kws
			worig_kptnums, wop_nums, wsymmops, trs = wf.get_kpt_mapping(allkpts)
			wops, wdrs = make_c_ops(wop_nums, wsymmops)
			wptr = cfunc_call(PAWC.expand_symm_wf, None, wf.pwf.wf_ptr,
				len(worig_kptnums), worig_kptnums, wops, wdrs, weights, trs)
			wf = copy_wf(wf, wptr, allkpts, weights, False, True)
		elif unsym_basis and not unsym_wf:
			allkpts = wf.pwf.kpts
			weights = wf.pwf.kws
			borig_kptnums, bop_nums, bsymmops, trs = basis.get_kpt_mapping(allkpts)
			bops, bdrs = make_c_ops(bop_nums, bsymmops)
			bptr = cfunc_call(PAWC.expand_symm_wf, None, basis.pwf.wf_ptr,
				len(borig_kptnums), borig_kptnums, bops, bdrs, weights, trs)
			basis = copy_wf(basis, bptr, allkpts, weights, False, True)

		if np.linalg.norm(basis.kpts - wf.kpts) > 1e-10:
			raise PAWpyError("k-point grids for projection are not matched.")
		if np.linalg.norm(basis.kws - wf.kws) > 1e-10:
			raise PAWpyError("k-point weights for projection are not matched.")
		
		if (wf.nums is None) and (not pseudo) and (not projector_list is None):
			selfnums = np.array([basis.labels[el(s)] for s in wf.structure], dtype=np.int32)
			selfcoords = np.array([], np.float64)
			for s in wf.structure:
				selfcoords = np.append(selfcoords, s.frac_coords)
			wf.nums = selfnums
			wf.coords = selfcoords
			wf.num_proj_els = basis.num_proj_els

		self.structure = wf.structure
		self.pwf = wf.pwf
		self.cr = wf.cr
		self.dim = wf.dim
		self.projector_owner = True
		self.projector_list = projector_list
		self.nband = wf.nband
		self.nwk = wf.nwk
		self.nspin = wf.nspin
		self.nums = wf.nums
		self.coords = wf.coords
		self.basis = basis
		self.wf = wf
		self.num_proj_els = wf.num_proj_els

		if not pseudo:
			self.setup_projection(basis, projector_list == None)
		self.pseudo=pseudo

	@staticmethod
	def from_files(basis, struct="CONTCAR", pwf="WAVECAR", cr="POTCAR",
		vr="vasprun.xml", outcar="OUTCAR", projector_list = None,
		unsym_basis = False, unsym_wf = False, pseudo = False):
		"""
		Construct a Projector object from file paths.
		Arguments:
			basis (Wavefunction): the basis Wavefunction
			struct (str): VASP POSCAR or CONTCAR file path
			pwf (str): VASP WAVECAR file path
			vr (str): VASP vasprun file path
			outcar (str): VASP OUTCAR file path
			setup_basis (bool): whether to set up the basis
		Returns:
			Projector object
		"""
		wf = Wavefunction(Poscar.from_file(struct).structure,
			PseudoWavefunction(pwf, vr),
			CoreRegion(Potcar.from_file(cr)),
			Outcar(outcar), projector_list)
		return Projector(wf, basis, projector_list,
			unsym_basis, unsym_wf, pseudo)

	@staticmethod
	def from_directory(basis, path, projector_list = None,
		unsym_basis = False, unsym_wf = False, pseudo = False):
		"""
		Assumes VASP output has the default filenames and is located
		in the directory specificed by path.
		Arguments:
			basis (Wavefunction): the basis Wavefunction
			path (str): path to the VASP calculation directory
			setup_basis (bool): whether to set up the basis
		Returns:
			Projector object
		"""
		filepaths = []
		for d in ["CONTCAR", "WAVECAR", "POTCAR", "vasprun.xml", "OUTCAR"]:
			filepaths.append(str(os.path.join(path, d)))
		args = [basis] + filepaths + [projector_list, unsym_basis, unsym_wf, pseudo]
		return Projector.from_files(*args)

	def make_site_lists(self, basis):
		"""
		Organizes sites into sets for use in the projection scheme. M_R and M_S contain site indices
		of sites which are identical in structures R (basis) and S (self). N_R and N_S contain all other
		site indices, and N_RS contains pairs of indices in R and S with overlapping augmentation
		spheres in the PAW formalism.

		Arguments:
			basis (Wavefunction object): Wavefunction in the same lattice as self.
				The bands in self will be projected onto the bands in basis
		Returns:
			M_R (numpy array): Indices of sites in basis which have an identical site in
				S (self) (same element and position to within tolerance of 0.02 Angstroms).
			M_S (numpy array): Indices of sites in self which match sites in M_R
				(i.e. M_R[i] is an identical site to M_S[i])
			N_R (numpy array): Indices of sites in basis but not in M_R
			N_S (numpy array): Indices of sites in self but not in M_S
			N_RS (numpy array): Pairs of indices (one in basis and one in self) which
				are not identical but have overlapping augmentation regions
		"""
		ref_sites = basis.structure.sites
		sites = self.structure.sites
		M_R = []
		M_S = []
		for i in range(len(ref_sites)):
			for j in range(len(sites)):
				if ref_sites[i].distance(sites[j]) <= 0.02 and el(ref_sites[i]) == el(sites[j]):
					M_R.append(i)
					M_S.append(j)
		N_R = []
		N_S = []
		for i in range(len(ref_sites)):
			if not i in M_R:
				N_R.append(i)
		for j in range(len(sites)):
			if (not j in N_S) and (not j in M_S):
				N_S.append(j)
		
		N_RS = []
		for i in N_R:
			for j in N_S:
				if ref_sites[i].distance(sites[j]) < self.cr.pps[el(ref_sites[i])].rmax + self.cr.pps[el(sites[j])].rmax:
					N_RS.append((i,j))
		return M_R, M_S, N_R, N_S, N_RS

	def setup_projection(self, basis, setup_basis=True):
		"""
		Evaluates projectors <p_i|psi>, as well
		as <(phi-phit)|psi> and <(phi_i-phit_i)|(phi_j-phit_j)>,
		when needed

		Arguments:
			basis (Wavefunction): wavefunction onto which bands of self
			will be projected.
		"""

		#if not basis.projection_data:
		#	basis.projection_data = self.make_c_projectors(basis)
		#projector_list, selfnums, selfcoords, basisnums, basiscoords = basis.projection_data
		if setup_basis:
			self.projector_list, self.nums, self.coords,\
				basis.nums, basis.coords = self.make_c_projectors(basis)
		projector_list = self.projector_list
		basisnums = basis.nums
		basiscoords = basis.coords
		selfnums = self.nums
		selfcoords = self.coords

		print(hex(projector_list), hex(self.pwf.wf_ptr))
		sys.stdout.flush()
		print ("TYPETHING", basis.pwf.wf_ptr, type(basis.pwf.wf_ptr))
		
		if setup_basis:
			cfunc_call(PAWC.setup_projections_no_rayleigh, None,
						basis.pwf.wf_ptr, projector_list,
						self.num_proj_els, len(basis.structure), self.dim,
						basisnums, basiscoords)
		start = time.monotonic()
		#basis.pwf.wf_ptr
		cfunc_call(PAWC.setup_projections_no_rayleigh, None,
					self.pwf.wf_ptr,
					projector_list, self.num_proj_els, len(self.structure),
					self.dim, selfnums, selfcoords)
		end = time.monotonic()
		print('--------------\nran setup_projections in %f seconds\n---------------' % (end-start))
		Timer.setup_time(end-start)
		M_R, M_S, N_R, N_S, N_RS = self.make_site_lists(basis)
		num_N_RS = len(N_RS)
		if num_N_RS > 0:
			N_RS_R, N_RS_S = zip(*N_RS)
		else:
			N_RS_R, N_RS_S = [], []
		self.site_cat = [M_R, M_S, N_R, N_S, N_RS_R, N_RS_S]
		start = time.monotonic()
		cfunc_call(PAWC.overlap_setup_real, None, basis.pwf.wf_ptr, self.pwf.wf_ptr,
					projector_list, basisnums, selfnums, basiscoords, selfcoords,
					N_R, N_S, N_RS_R, N_RS_S, len(N_R), len(N_S), len(N_RS_R))
		end = time.monotonic()
		Timer.overlap_time(end-start)
		print('-------------\nran overlap_setup in %f seconds\n---------------' % (end-start))

	def single_band_projection(self, band_num):
		"""
		All electron projection of the band_num band of self
		onto all the bands of basis. Returned as a numpy array,
		with the overlap operator matrix elements ordered as follows:
		loop over band
			loop over spin
				loop over kpoint

		Arguments:
			band_num (int): band which is projected onto basis

		Returns:
			res (np.array): overlap operator expectation values
				as described above
		"""

		if self.pseudo:
			return self.pwf.pseudoprojection(band_num, self.basis.pwf)

		basis = self.basis
		nband = basis.nband
		nwk = basis.nwk
		nspin = basis.nspin
		res = cfunc_call(PAWC.pseudoprojection, 2*nband*nwk*nspin,
						basis.pwf.wf_ptr, self.pwf.wf_ptr, band_num)
		print("datsa", nband, nwk, nspin)
		sys.stdout.flush()
		projector_list = self.projector_list
		basisnums = basis.nums
		basiscoords = basis.coords
		selfnums = self.nums
		selfcoords = self.coords

		M_R, M_S, N_R, N_S, N_RS_R, N_RS_S = self.site_cat
		
		start = time.monotonic()
		ct = cfunc_call(PAWC.compensation_terms, 2*nband*nwk*nspin,
						band_num, self.pwf.wf_ptr, basis.pwf.wf_ptr,
						projector_list, len(self.cr.pps),
						len(M_R), len(N_R), len(N_S), len(N_RS_R),
						M_R, M_S, N_R, N_S, N_RS_R, N_RS_S,
						selfnums, selfcoords, basisnums, basiscoords,
						self.dim)
		end = time.monotonic()
		Timer.augmentation_time(end-start)
		print('---------\nran compensation_terms in %f seconds\n-----------' % (end-start))
		res += ct
		return res[::2] + 1j * res[1::2]

	@staticmethod
	def setup_bases(basis_dirs, wf_dirs, desymmetrize = True):
		"""
		This function performs the setup of all the bases in the basis_dirs.
		After this function is called, pass the returned projector_list
		each time you call Projector with one of the wavefunctions in the
		basis_dirs list. Free projector_list after you are fully finished
		using the wavefunctions in basis_dirs for projections.
		"""

		bases = []
		crs = []
		for bdir in basis_dirs:
			basis = Wavefunction.from_directory(bdir)

			if desymmetrize:
				allkpts, borig_kptnums, bop_nums, bsymmops, trs = basis.get_nosym_kpoints()
				weights = np.ones(allkpts.shape[0]) / allkpts.shape[0]
				bops, bdrs = make_c_ops(bop_nums, bsymmops)
				bptr = cfunc_call(PAWC.expand_symm_wf, None, basis.pwf.wf_ptr,
					len(borig_kptnums), borig_kptnums, bops, bdrs, weights, trs)
				basis = copy_wf(basis, bptr, allkpts, weights, False, True)

			crs.append(basis.cr)
			bases.append(basis)

		crs += [CoreRegion(Potcar.from_file(os.path.join(wf_dir, 'POTCAR'))) \
			for wf_dir in wf_dirs]

		pps = {}
		labels = {}
		label = 0
		for cr in crs:
			for e in cr.pps:
				if not e in labels:
					pps[label] = cr.pps[e]
					labels[e] = label
					label = label + 1

		projector_list = basis.get_c_projectors_from_pps(pps)
		for basis in bases:
			basisnums = np.array([labels[el(s)] for s in basis.structure], dtype=np.int32)
			basiscoords = np.array([], np.float64)
			for s in basis.structure:
				basiscoords = np.append(basiscoords, s.frac_coords)
			basis.labels = labels
			basis.nums = basisnums
			basis.coords = basiscoords
			basis.num_proj_els = len(pps)

			cfunc_call(PAWC.setup_projections, None,
					basis.pwf.wf_ptr, projector_list, label,
					len(basis.structure), basis.dim, basisnums, basiscoords)

		return projector_list, bases

	@staticmethod
	def setup_multiple_projections(basis_dir, wf_dirs, pseudo = False, ignore_errors = False,
									desymmetrize = False):
		"""
		A convenient generator function for processing the Kohn-Sham wavefunctions
		of multiple structures with respect to one structure used as the basis.
		All C memory is freed after each yield for the wavefunctions to be analyzed,
		and C memory associated with the basis wavefunction is freed when
		the generator is called after all wavefunctions have been yielded.

		Args:
			basis_dir (str): path to the VASP output to be used as the basis structure
			wf_dirs (list of str): paths to the VASP outputs to be analyzed
			ignore_errors (bool, False): whether to ignore errors in setting up
				Wavefunction objects by skipping over the directories for which
				setup fails.

		Returns:
			list -- wf_dir, basis, wf
			Each iteration of the generator function returns a directory name from
			wf_dirs (wf_dir), the basis Wavefunction object (basis), and the Wavefunction
			object associated with wf_dir (wf), fully setup to project bands of wf
			onto bands of basis.
		"""

		basis = Wavefunction.from_directory(basis_dir, False)
		if desymmetrize:
			allkpts, borig_kptnums, bop_nums, bsymmops, trs = basis.get_nosym_kpoints()
			weights = np.ones(allkpts.shape[0]) / allkpts.shape[0]
			bops, bdrs = make_c_ops(bop_nums, bsymmops)
			bptr = cfunc_call(PAWC.expand_symm_wf, None, basis.pwf.wf_ptr,
				len(borig_kptnums), borig_kptnums, bops, bdrs, weights, trs)
			basis = copy_wf(basis, bptr, allkpts, weights, False, True)
		
		crs = [basis.cr] + [CoreRegion(Potcar.from_file(os.path.join(wf_dir, 'POTCAR'))) \
			for wf_dir in wf_dirs]

		pps = {}
		labels = {}
		label = 0
		for cr in crs:
			for e in cr.pps:
				if not e in labels:
					pps[label] = cr.pps[e]
					labels[e] = label
					label = label + 1

		#print (pps)
		projector_list = basis.get_c_projectors_from_pps(pps)
		basisnums = np.array([labels[el(s)] for s in basis.structure], dtype=np.int32)
		basiscoords = np.array([], np.float64)
		for s in basis.structure:
			basiscoords = np.append(basiscoords, s.frac_coords)
		basis.nums = basisnums
		basis.coords = basiscoords
		basis.num_proj_els = len(pps)

		sys.stdout.flush()	
		#PAWC.setup_projections(c_void_p(basis.pwf.wf_ptr),
		#	c_void_p(projector_list), label,
		#	len(basis.structure), numpy_to_cint(basis.dim), numpy_to_cint(basisnums),
		#	numpy_to_cdouble(basiscoords))
		cfunc_call(PAWC.setup_projections, None,
					basis.pwf.wf_ptr, projector_list, label,
					len(basis.structure), basis.dim, basisnums, basiscoords)

		errcount = 0
		pr = None
		for wf_dir, cr in zip(wf_dirs, crs[1:]):

			try:
				files = {}
				for f in ['CONTCAR', 'OUTCAR', 'vasprun.xml', 'WAVECAR']:
					files[f] = os.path.join(wf_dir, f)
				struct = Poscar.from_file(files['CONTCAR']).structure
				pwf = PseudoWavefunction(files['WAVECAR'], files['vasprun.xml'])
				outcar = Outcar(files['OUTCAR'])

				wf = Wavefunction(struct, pwf, cr, outcar, False)

				selfnums = np.array([labels[el(s)] for s in wf.structure], dtype=np.int32)
				selfcoords = np.array([], np.float64)

				for s in wf.structure:
					selfcoords = np.append(selfcoords, s.frac_coords)
				wf.nums = selfnums
				wf.coords = selfcoords
				wf.num_proj_els = len(pps)

				if desymmetrize:
					pr = Projector(wf, basis, projector_list, pseudo = pseudo, unsym_wf = True)
				else:
					pr = Projector(wf, basis, projector_list, pseudo = pseudo)

				yield [wf_dir, pr]
				wf.free_all()
			except Exception as e:
				if ignore_errors:
					errcount += 1
				else:
					raise PAWpyError('Unable to setup wavefunction in directory %s' % wf_dir\
										+'\nGot the following error:\n'+str(e))
		basis.free_all()
		if pr:
			pr.free_all()
		else:
			raise PAWpyError("Could not generate any projector setups")
		print("Number of errors:", errcount)

	def proportion_conduction(self, band_num, spinpol = False):
		"""
		Calculates the proportion of band band_num in self
		that projects onto the valence states and conduction
		states of self.basis (should be the bulk structure).
		Designed for analysis of point defect
		wavefunctions.

		Arguments:
			band_num (int): number of defect band in self

		Returns:
			v, c (int, int): The valence (v) and conduction (c)
				proportion of band band_num
		"""
		basis = self.basis
		nband = basis.nband
		nwk = basis.nwk
		nspin = basis.nspin
		occs = cdouble_to_numpy(PAWC.get_occs(c_void_p(basis.pwf.wf_ptr)), nband*nwk*nspin)

		res = self.single_band_projection(band_num)

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
		if self.pseudo:
			t = v+c
			v /= t
			c /= t
		if spinpol:
			v = v.tolist()
			c = c.tolist()
		return v, c

	def defect_band_analysis(self, num_below_ef=20,
		num_above_ef=20, spinpol = False, return_energies = False):
		"""
		Identifies a set of 'interesting' bands in a defect structure
		to analyze by choosing any band that is more than bound conduction
		and more than bound valence in the pseudoprojection scheme,
		and then fully analyzing these bands using single_band_projection

		Args:
			num_below_ef (int, 20): number of bands to analyze below the fermi level
			num_above_ef (int, 20): number of bands to analyze above the fermi level
			spinpol (bool, False): whether to return spin-polarized results (only allowed
				for spin-polarized DFT output)
		"""
		basis = self.basis
		nband = basis.nband
		nwk = basis.nwk
		nspin = basis.nspin
		#totest = set()
		occs = cdouble_to_numpy(PAWC.get_occs(c_void_p(self.pwf.wf_ptr)), self.nband*self.nwk*self.nspin)
		vbm = 0
		print(occs)
		for i in range(self.nband):
			if occs[i*self.nwk*self.nspin] > 0.5:
				vbm = i
		min_band, max_band = vbm - num_below_ef, vbm + num_above_ef
		if min_band < 0 or max_band >= nband:
			raise PAWpyError("The min or max band is too large/small with min_band=%d, max_band=%d, nband=%d" \
				% (min_band, max_band, nband))
		"""
		for b in range(nband):
			v, c = self.proportion_conduction(b, basis, spinpol = False)
			if v > bound and c > bound:
				totest.add(b)
				totest.add(b-1)
				totest.add(b+1)
		"""
		totest = [i for i in range(min_band,max_band+1)]
		print("NUM TO TEST", len(totest))

		results = {}
		energies = {}
		for b in totest:
			results[b] = self.proportion_conduction(b, spinpol = spinpol)
			energies[b] = 0
			for k in range(self.nwk):
				for s in range(self.nspin):
					energies[b] += cfunc_call(PAWC.get_energy, None, self.pwf.wf_ptr, b, k, s) * self.pwf.kws[k]
			energies[b] /= np.sum(self.pwf.kws) * self.nspin 

		if return_energies:
			return results, energies
		return results

	@staticmethod
	def free_projector_list(projector_list, num_elems):
		"""
		If you generate a projector_list using the setup_bases method,
		you can free it easily by calling

		>>> Projector.free_projector_list(projector_list, basis.num_proj_els)
		
		where basis is one of the Wavefunction objects returned by setup_bases
		and projector_list is the C pointer of the same name returned by setup_bases
		"""
		
		PAWC.free_ppot_list(c_void_p(projector_list), num_elems)

	def free_all(self):
		"""
		Frees all of the C structures associated with the Wavefunction object.
		After being called, this object is not usable.
		"""
		PAWC.free_ppot_list(c_void_p(self.projector_list), len(self.cr.pps))
