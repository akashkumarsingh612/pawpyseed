#include <stdio.h>
#include <stdlib.h>
#include <complex.h>
#include <math.h>
#include <omp.h>
#include <time.h>
#include <mkl.h>
#include <mkl_types.h>
#include "utils.h"
#include "fft.h"

#define PI 3.14159265359

void trilinear_interpolate_values(MKL_Complex16* x, double* frac, int* fftg, double complex* values) {
	//values: c000, c001, c010, c011, c100, c101, c110, c111
	int i = (int) (frac[0] * fftg[0]);
	int j = (int) (frac[1] * fftg[1]);
	int k = (int) (frac[2] * fftg[2]);
	int ip = (i+1)%fftg[0];
	int jp = (j+1)%fftg[1];
	int kp = (k+1)%fftg[2];

	int ind[8];
	ind[0] = i*fftg[1]*fftg[2] + j*fftg[2] + k;
	ind[1] = i*fftg[1]*fftg[2] + j*fftg[2] + kp;
	ind[2] = i*fftg[1]*fftg[2] + jp*fftg[2] + k;
	ind[3] = i*fftg[1]*fftg[2] + jp*fftg[2] + kp;
	ind[4] = ip*fftg[1]*fftg[2] + j*fftg[2] + k;
	ind[5] = ip*fftg[1]*fftg[2] + j*fftg[2] + kp;
	ind[6] = ip*fftg[1]*fftg[2] + jp*fftg[2] + k;
	ind[7] = ip*fftg[1]*fftg[2] + jp*fftg[2] + kp;
	for (int n = 0; n < 8; n++) values[n] = x[ind[n]].real + I * x[ind[n]].imag;
}

void fft3d(MKL_Complex16* x, int* G_bounds, double* lattice,
	double* kpt, int* Gs, float complex* Cs, int num_waves, int* fftg) {

	MKL_LONG status = 0;
	DFTI_DESCRIPTOR_HANDLE handle = 0;
	MKL_LONG dim = 3;
	MKL_LONG length[3] = {fftg[0], fftg[1], fftg[2]};

	//double test_total = 0;
	for (int w = 0; w < num_waves; w++) {
		int g1 = Gs[3*w]-G_bounds[0], g2 = Gs[3*w+1]-G_bounds[2], g3 = Gs[3*w+2]-G_bounds[4];
		x[g1*fftg[1]*fftg[2] + g2*fftg[2] + g3].real = creal(Cs[w]);
		x[g1*fftg[1]*fftg[2] + g2*fftg[2] + g3].imag = cimag(Cs[w]);
		//test_total += cabs(Cs[w]) * cabs(Cs[w]);
	}

	MKL_LONG status1 = DftiCreateDescriptor(&handle, DFTI_DOUBLE, DFTI_COMPLEX, dim, length);
	MKL_LONG status2 = DftiCommitDescriptor(handle);
	MKL_LONG status3 = DftiComputeBackward(handle, x);
	//printf("%s\n%s\n%s\n", DftiErrorMessage(status1), DftiErrorMessage(status2), DftiErrorMessage(status3));

	//double kmins[3] = {G_bounds[0] + kpt[0], G_bounds[2] + kpt[1], G_bounds[4] + kpt[2]};
	double kmins[3] = {G_bounds[0], G_bounds[2], G_bounds[4]};
	double dv = determinant(lattice) / fftg[0] / fftg[1] / fftg[2];
	double inv_sqrt_vol = pow(determinant(lattice), -0.5);

	double frac[3] = {0,0,0};
	double kdotr = 0;

	double total = 0;
	double rp, ip;
	for (int i = 0; i < fftg[0]; i++) {
		for (int j = 0; j < fftg[1]; j++) {
			for (int k = 0; k  < fftg[2]; k++) {
				frac[0] = ((double)i)/fftg[0];
				frac[1] = ((double)j)/fftg[1];
				frac[2] = ((double)k)/fftg[2];
				kdotr = 2 * PI * dot(kmins, frac);
				rp = x[i*fftg[1]*fftg[2] + j*fftg[2] + k].real * inv_sqrt_vol;
				ip = x[i*fftg[1]*fftg[2] + j*fftg[2] + k].imag * inv_sqrt_vol;
				x[i*fftg[1]*fftg[2] + j*fftg[2] + k].real = rp * cos(kdotr) - ip * sin(kdotr);
				x[i*fftg[1]*fftg[2] + j*fftg[2] + k].imag = ip * cos(kdotr) + rp * sin(kdotr);
				total += (pow(x[i*fftg[1]*fftg[2] + j*fftg[2] + k].real, 2)
					+ pow(x[i*fftg[1]*fftg[2] + j*fftg[2] + k].imag, 2)) * dv;
			}
		}
	}
	
	DftiFreeDescriptor(&handle);
	//printf("total %lf\n",total);
}
