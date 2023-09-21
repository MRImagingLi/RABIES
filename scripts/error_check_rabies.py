#! /usr/bin/env python

import SimpleITK as sitk
import os
import sys
import numpy as np
import tempfile
import shutil
import subprocess
from rabies.utils import resample_image_spacing, copyInfo_4DImage

if len(sys.argv) == 2:
    tmppath = sys.argv[1]
else:
    tmppath = tempfile.mkdtemp()

def generate_token_data(tmppath, number_scans):

    os.makedirs(tmppath+'/inputs', exist_ok=True)

    if 'XDG_DATA_HOME' in os.environ.keys():
        rabies_path = os.environ['XDG_DATA_HOME']+'/rabies'
    else:
        rabies_path = os.environ['HOME']+'/.local/share/rabies'

    template = f"{rabies_path}/DSURQE_40micron_average.nii.gz"
    mask = f"{rabies_path}/DSURQE_40micron_mask.nii.gz"

    spacing = (float(1), float(1), float(1))  # resample to 1mmx1mmx1mm
    resampled_template = resample_image_spacing(sitk.ReadImage(template), spacing)
    # generate template masks
    resampled_mask = resample_image_spacing(sitk.ReadImage(mask), spacing)
    array = sitk.GetArrayFromImage(resampled_mask)
    array[array < 1] = 0
    array[array > 1] = 1
    binarized = sitk.GetImageFromArray(array, isVector=False)
    binarized.CopyInformation(resampled_mask)
    sitk.WriteImage(binarized, tmppath+'/inputs/token_mask.nii.gz')
    array[:, :, :6] = 0
    binarized = sitk.GetImageFromArray(array, isVector=False)
    binarized.CopyInformation(resampled_mask)
    sitk.WriteImage(binarized, tmppath+'/inputs/token_mask_half.nii.gz')

    # generate fake scans from the template
    array = sitk.GetArrayFromImage(resampled_template)
    array_4d = np.repeat(array[np.newaxis, :, :, :], 15, axis=0)

    for i in range(number_scans):
        # generate anatomical scan
        sitk.WriteImage(resampled_template, tmppath+f'/inputs/sub-token{i+1}_T1w.nii.gz')
        # generate functional scan
        array_4d_ = array_4d + np.random.normal(0, array_4d.mean()
                                    / 100, array_4d.shape)  # add gaussian noise
        sitk.WriteImage(sitk.GetImageFromArray(array_4d_, isVector=False),
                        tmppath+f'/inputs/sub-token{i+1}_bold.nii.gz')

        sitk.WriteImage(copyInfo_4DImage(sitk.ReadImage(tmppath+f'/inputs/sub-token{i+1}_bold.nii.gz'), sitk.ReadImage(tmppath
                        + f'/inputs/sub-token{i+1}_T1w.nii.gz'), sitk.ReadImage(tmppath+f'/inputs/sub-token{i+1}_bold.nii.gz')), tmppath+f'/inputs/sub-token{i+1}_bold.nii.gz')


generate_token_data(tmppath, number_scans=1)

command = f"rabies --verbose 1 preprocess {tmppath}/inputs {tmppath}/outputs --anat_inho_cor method=disable,otsu_thresh=2,multiotsu=false --bold_inho_cor method=disable,otsu_thresh=2,multiotsu=false \
    --anat_template {tmppath}/inputs/sub-token1_T1w.nii.gz --brain_mask {tmppath}/inputs/token_mask.nii.gz --WM_mask {tmppath}/inputs/token_mask.nii.gz --CSF_mask {tmppath}/inputs/token_mask.nii.gz --vascular_mask {tmppath}/inputs/token_mask.nii.gz --labels {tmppath}/inputs/token_mask.nii.gz \
    --bold2anat_coreg registration=no_reg,masking=false,brain_extraction=false --commonspace_reg masking=false,brain_extraction=false,fast_commonspace=true,template_registration=no_reg --data_type int16 --bold_only --detect_dummy \
    --tpattern seq-z --apply_STC --voxelwise_motion --isotropic_HMC"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

shutil.rmtree(f'{tmppath}/outputs/')
command = f"rabies --verbose 1 preprocess {tmppath}/inputs {tmppath}/outputs --anat_inho_cor method=disable,otsu_thresh=2,multiotsu=false --bold_inho_cor method=disable,otsu_thresh=2,multiotsu=false \
    --anat_template {tmppath}/inputs/sub-token1_T1w.nii.gz --brain_mask {tmppath}/inputs/token_mask.nii.gz --WM_mask {tmppath}/inputs/token_mask.nii.gz --CSF_mask {tmppath}/inputs/token_mask.nii.gz --vascular_mask {tmppath}/inputs/token_mask.nii.gz --labels {tmppath}/inputs/token_mask.nii.gz \
    --bold2anat_coreg registration=no_reg,masking=true,brain_extraction=true --commonspace_reg masking=true,brain_extraction=true,fast_commonspace=true,template_registration=no_reg --data_type int16  \
    --HMC_option 0"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

command = f"rabies --verbose 1 confound_correction {tmppath}/outputs {tmppath}/outputs --ica_aroma apply=true,dim=0,random_seed=1 --frame_censoring FD_censoring=true,FD_threshold=0.05,DVARS_censoring=true,minimum_timepoint=3 --nativespace_analysis"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

#command = f"rabies --verbose 1 analysis {tmppath}/outputs {tmppath}/outputs --data_diagnosis"
#process = subprocess.run(
#    command,
#    check=True,
#    shell=True,
#    )

shutil.rmtree(f'{tmppath}/inputs/')
generate_token_data(tmppath, number_scans=3)

shutil.rmtree(f'{tmppath}/outputs/')
command = f"rabies --verbose 1 preprocess {tmppath}/inputs {tmppath}/outputs --anat_inho_cor method=disable,otsu_thresh=2,multiotsu=false --bold_inho_cor method=disable,otsu_thresh=2,multiotsu=false \
    --anat_template {tmppath}/inputs/sub-token1_T1w.nii.gz --brain_mask {tmppath}/inputs/token_mask.nii.gz --WM_mask {tmppath}/inputs/token_mask_half.nii.gz --CSF_mask {tmppath}/inputs/token_mask_half.nii.gz --vascular_mask {tmppath}/inputs/token_mask_half.nii.gz --labels {tmppath}/inputs/token_mask.nii.gz \
    --bold2anat_coreg registration=no_reg,masking=false,brain_extraction=false --commonspace_reg masking=false,brain_extraction=false,fast_commonspace=true,template_registration=no_reg --data_type int16  \
    --HMC_option 0"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

command = f"rabies --verbose 1 confound_correction --read_datasink {tmppath}/outputs {tmppath}/outputs --conf_list mot_6 --smoothing_filter 0.3"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

command = f"rabies --verbose 1 analysis {tmppath}/outputs {tmppath}/outputs --DR_ICA --NPR_temporal_comp 1 --seed_list {tmppath}/inputs/token_mask_half.nii.gz"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

shutil.rmtree(f'{tmppath}/outputs/confound_correction_main_wf')
shutil.rmtree(f'{tmppath}/outputs/confound_correction_datasink')
os.remove(f'{tmppath}/outputs/rabies_confound_correction.pkl')
command = f"rabies --verbose 1 confound_correction {tmppath}/outputs {tmppath}/outputs"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )

shutil.rmtree(f'{tmppath}/outputs/analysis_main_wf')
shutil.rmtree(f'{tmppath}/outputs/analysis_datasink')
os.remove(f'{tmppath}/outputs/rabies_analysis.pkl')
command = f"rabies --verbose 1 analysis {tmppath}/outputs {tmppath}/outputs --NPR_temporal_comp 1 --data_diagnosis --DR_ICA"
process = subprocess.run(
    command,
    check=True,
    shell=True,
    )


if not len(sys.argv) == 2:
    shutil.rmtree(tmppath)
