#include <stdio.h>
#include <stdlib.h>
#include <complex.h>
#include <math.h>
#include <omp.h>
#include <time.h>
#include "utils.c"

#define PI 3.14159265359
#define c 0.262465831

void vc_pseudoprojection(pswf_t* wf_ref, pswf_t* wf_proj, int BAND_NUM, double* results) {

	clock_t start = clock();
	kpoint_t** kpts = wf_ref->kpts;
	kpoint_t** kptspro = wf_proj->kpts;
	int NUM_KPTS = wf_ref->nwk * wf_ref->nspin;
	int NUM_BANDS = wf_ref->nband;

	double* cband = (double*) calloc(NUM_KPTS, sizeof(double));
	double* vband = (double*) calloc(NUM_KPTS, sizeof(double));

	#pragma omp parallel for 
	for (int b = 0; b < NUM_BANDS; b++)
	{
		//printf("occ %d %lf\n", b, kpts[0]->bands[b]->occ);
		for (int kpt_num = 0; kpt_num < NUM_KPTS; kpt_num++)
		{
			float complex curr_overlap = 0;
			float complex* C1s = kptspro[kpt_num]->bands[0]->Cs;
			float complex* C2s = kpts[kpt_num]->bands[b]->Cs;
			int num_waves = kpts[kpt_num]->bands[b]->num_waves;
			for (int w = 0; w < num_waves; w++)
			{
				curr_overlap += C1s[w] * conj(C2s[w]);
			}
			#pragma omp critical
			{
				if (kpts[kpt_num]->bands[b]->occ > 0.5)
					vband[kpt_num] += creal((double) (curr_overlap * conj(curr_overlap)));
				else
					cband[kpt_num] += creal((double) (curr_overlap * conj(curr_overlap)));
			}
		}
	}

	double ctotal = 0.0;
	double vtotal = 0.0;
	for (int kpt_num = 0; kpt_num < NUM_KPTS; kpt_num++) {
		//printf("%lf %lf\n", cband[kpt_num], kpts[kpt_num]->weight);
		ctotal += cband[kpt_num] * kpts[kpt_num]->weight;
		vtotal += vband[kpt_num] * kpts[kpt_num]->weight;
	}

	printf("%lf\n", creal(kptspro[0]->bands[0]->energy));
	printf("c %lf\n", ctotal);
	printf("v %lf\n", vtotal);

	free(vband);
	free(cband);
	results[0] = vtotal;
	results[1] = ctotal;

	clock_t end = clock();
	printf("%lf seconds for band projection\n", (double)(end - start) / CLOCKS_PER_SEC);

}

double* pseudoprojection(pswf_t* wf_ref, pswf_t* wf_proj, int BAND_NUM) {

	kpoint_t** kpts = wf_ref->kpts;
	kpoint_t** kptspro = wf_proj->kpts;
	int NUM_KPTS = wf_ref->nwk * wf_ref->nspin;
	int NUM_BANDS = wf_ref->nband;

	float complex* projections = (float complex*) malloc(NUM_BANDS*NUM_KPTS*sizeof(float complex));

	#pragma omp parallel for 
	for (int b = 0; b < NUM_BANDS; b++)
	{
		//printf("occ %d %lf\n", b, kpts[0]->bands[b]->occ);
		for (int kpt_num = 0; kpt_num < NUM_KPTS; kpt_num++)
		{
			float complex curr_overlap = 0;
			float complex* C1s = kptspro[kpt_num]->bands[0]->Cs;
			float complex* C2s = kpts[kpt_num]->bands[b]->Cs;
			int num_waves = kpts[kpt_num]->bands[b]->num_waves;
			for (int w = 0; w < num_waves; w++)
			{
				curr_overlap += C1s[w] * conj(C2s[w]);
			}
			projections[b*NUM_KPTS+kpt_num] = curr_overlap;
		}
	}

	return projections;
}

double* read_and_project(int BAND_NUM, double* kpt_weights, char* bulkfile, char* defectfile) {
	printf("%lf\n", kpt_weights[0]);
	printf("%lf\n", kpt_weights[1]);
	printf("%lf\n", kpt_weights[5]);
	int* G_bounds = (int*) malloc(6*sizeof(double));
	double* results = (double*) malloc(2*sizeof(double));
	int NUM_SPINS, NUM_KPTS, NUM_BANDS;
	kpoint_t** kptspro = read_one_band(G_bounds, kpt_weights, &NUM_SPINS, &NUM_KPTS, &NUM_BANDS, BAND_NUM, defectfile);
	kpoint_t** kptsref = read_wavefunctions(G_bounds, kpt_weights, &NUM_SPINS, &NUM_KPTS, &NUM_BANDS, bulkfile);
	get_band_projection(BAND_NUM, NUM_KPTS, NUM_BANDS, kptsref, kptspro, G_bounds, results);
	for (int kpt_num = 0; kpt_num < NUM_KPTS; kpt_num++) {
		//printf("%d\n", kpt_num);
		free_kpoint(kptsref[kpt_num]);
		free_kpoint(kptspro[kpt_num]);
	}
	free(kptsref);
	free(kptspro);
	free(G_bounds);
	return results;
}
