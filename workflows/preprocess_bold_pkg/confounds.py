import os
from nipype.pipeline import engine as pe
from nipype.interfaces import utility as niu
from nipype.interfaces.base import (
    traits, TraitedSpec, BaseInterfaceInputSpec,
    File, BaseInterface
)
from nipype import Function

def init_bold_confs_wf(TR, SyN_SDC, aCompCor_method='50%', name="bold_confs_wf"):

    inputnode = pe.Node(niu.IdentityInterface(
        fields=['bold', 'ref_bold', 'movpar_file', 't1_mask', 't1_labels', 'WM_mask', 'CSF_mask']),
        name='inputnode')
    outputnode = pe.Node(niu.IdentityInterface(
        fields=['cleaned_bold', 'GSR_cleaned_bold', 'EPI_labels', 'confounds_csv']),
        name='outputnode')

    WM_mask_to_EPI=pe.Node(MaskEPI(SyN_SDC=SyN_SDC), name='WM_mask_EPI')
    WM_mask_to_EPI.inputs.name_spec='WM_mask'

    CSF_mask_to_EPI=pe.Node(MaskEPI(SyN_SDC=SyN_SDC), name='CSF_mask_EPI')
    CSF_mask_to_EPI.inputs.name_spec='WM_mask'

    brain_mask_to_EPI=pe.Node(MaskEPI(SyN_SDC=SyN_SDC), name='Brain_mask_EPI')
    brain_mask_to_EPI.inputs.name_spec='brain_mask'

    propagate_labels=pe.Node(MaskEPI(SyN_SDC=SyN_SDC), name='prop_labels_EPI')
    propagate_labels.inputs.name_spec='anat_labels'

    confound_regression=pe.Node(ConfoundRegression(aCompCor_method=aCompCor_method, TR=TR), name='confound_regression')

    workflow = pe.Workflow(name=name)
    workflow.connect([
        (inputnode, WM_mask_to_EPI, [
            ('WM_mask', 'mask'),
            ('ref_bold', 'ref_EPI')]),
        (inputnode, CSF_mask_to_EPI, [
            ('CSF_mask', 'mask'),
            ('ref_bold', 'ref_EPI')]),
        (inputnode, brain_mask_to_EPI, [
            ('t1_mask', 'mask'),
            ('ref_bold', 'ref_EPI')]),
        (inputnode, propagate_labels, [
            ('t1_labels', 'mask'),
            ('ref_bold', 'ref_EPI')]),
        (inputnode, confound_regression, [
            ('movpar_file', 'movpar_file'),
            ]),
        (inputnode, confound_regression, [
            ('bold', 'bold'),
            ]),
        (WM_mask_to_EPI, confound_regression, [
            ('EPI_mask', 'WM_mask')]),
        (CSF_mask_to_EPI, confound_regression, [
            ('EPI_mask', 'CSF_mask')]),
        (brain_mask_to_EPI, confound_regression, [
            ('EPI_mask', 'brain_mask')]),
        (propagate_labels, outputnode, [
            ('EPI_mask', 'EPI_labels')]),
        (confound_regression, outputnode, [
            ('confounds_csv', 'confounds_csv'),
            ]),
        ])

    return workflow

class ConfoundRegressionInputSpec(BaseInterfaceInputSpec):
    bold = File(exists=True, mandatory=True, desc="Preprocessed bold file to clean")
    movpar_file = File(exists=True, mandatory=True, desc="CSV file with the 6 rigid body parameters")
    brain_mask = File(exists=True, mandatory=True, desc="EPI-formated whole brain mask")
    WM_mask = File(exists=True, mandatory=True, desc="EPI-formated white matter mask")
    CSF_mask = File(exists=True, mandatory=True, desc="EPI-formated CSF mask")
    TR = traits.Float(mandatory=True, desc="Repetition time.")
    aCompCor_method = traits.Str(desc="The type of evaluation for the number of aCompCor components: either '50%' or 'first_5'.")

class ConfoundRegressionOutputSpec(TraitedSpec):
    confounds_csv = traits.File(desc="CSV file of confounds")

class ConfoundRegression(BaseInterface):

    input_spec = ConfoundRegressionInputSpec
    output_spec = ConfoundRegressionOutputSpec

    def _run_interface(self, runtime):
        import numpy as np
        import os
        subject_id=os.path.basename(self.inputs.bold).split('_ses-')[0]
        session=os.path.basename(self.inputs.bold).split('_ses-')[1][0]
        run=os.path.basename(self.inputs.bold).split('_run-')[1][0]
        filename_template = os.path.abspath('%s_ses-%s_run-%s' % (subject_id, session, run))

        confounds=[]
        csv_columns=[]
        WM_signal=extract_mask_trace(self.inputs.bold, self.inputs.WM_mask)
        confounds.append(WM_signal)
        csv_columns+=['WM_signal']
        [WM_aCompCor, num_comp]=compute_aCompCor(self.inputs.bold, self.inputs.WM_mask, method=self.inputs.aCompCor_method)
        for param in range(WM_aCompCor.shape[1]):
            confounds.append(WM_aCompCor[:,param])
        comp_column=[]
        for comp in range(num_comp):
            comp_column.append('WM_comp'+str(comp+1))
        csv_columns+=comp_column

        CSF_signal=extract_mask_trace(self.inputs.bold, self.inputs.CSF_mask)
        confounds.append(CSF_signal)
        csv_columns+=['CSF_signal']
        [CSF_aCompCor, num_comp]=compute_aCompCor(self.inputs.bold, self.inputs.CSF_mask, method=self.inputs.aCompCor_method)
        for param in range(CSF_aCompCor.shape[1]):
            confounds.append(CSF_aCompCor[:,param])
        comp_column=[]
        for comp in range(num_comp):
            comp_column.append('CSF_comp'+str(comp+1))
        csv_columns+=comp_column

        global_signal=extract_mask_trace(self.inputs.bold, self.inputs.brain_mask)
        confounds.append(global_signal)
        csv_columns+=['global_signal']
        motion_24=motion_24_params(self.inputs.movpar_file)
        for param in range(motion_24.shape[1]):
            confounds.append(motion_24[:,param])
        csv_columns+=['mov1-1', 'mov2-1', 'mov3-1', 'rot1-1', 'rot2-1', 'rot3-1', 'mov1^2', 'mov2^2', 'mov3^2', 'rot1^2', 'rot2^2', 'rot3^2', 'mov1-1^2', 'mov2-1^2', 'mov3-1^2', 'rot1-1^2', 'rot2-1^2', 'rot3-1^2']

        confounds_csv=write_confound_csv(np.transpose(np.asarray(confounds)), csv_columns, filename_template)

        setattr(self, 'confounds_csv', confounds_csv)
        return runtime

    def _list_outputs(self):
        return {'confounds_csv': getattr(self, 'confounds_csv')}

def write_confound_csv(confound_array, column_names, filename_template):
    import pandas as pd
    import os
    df = pd.DataFrame(confound_array)
    df.columns=column_names
    csv_path=os.path.abspath("%s_confounds.csv" % filename_template)
    df.to_csv(csv_path)
    return csv_path

def clean_bold(bold, confounds_array, TR):
    '''clean with nilearn'''
    import nilearn.image
    import os
    regressed_bold = nilearn.image.clean_img(bold, detrend=True, standardize=True, high_pass=0.01, confounds=confounds_array, t_r=TR)
    cleaned = nilearn.image.smooth_img(regressed_bold, 0.3)
    cleaned_path=os.path.abspath('cleaned.nii.gz')
    cleaned.to_filename(cleaned_path)
    return cleaned_path

def compute_aCompCor(bold, mask, method='50%'):
    '''
    Compute the anatomical comp corr through PCA over a defined ROI (mask) within
    the EPI, and retain either the first 5 components' time series or up to 50% of
    the variance explained as in Muschelli et al. 2014.
    '''
    import nibabel as nb
    from sklearn.decomposition import PCA

    from nilearn.input_data import NiftiMasker
    masker=NiftiMasker(mask_img=nb.load(mask), standardize=True, detrend=True) #detrend and standardize the voxel time series before PCA
    mask_timeseries=masker.fit_transform(nb.load(bold)) #shape n_timepoints x n_voxels

    if method=='50%':
        pca=PCA()
        pca.fit(mask_timeseries)
        explained_variance=pca.explained_variance_ratio_
        cum_var=0
        num_comp=0
        #evaluate the # of components to explain 50% of the variance
        while(cum_var<=0.5):
            cum_var+=explained_variance[num_comp]
            num_comp+=1
    elif method=='first_5':
        num_comp=5

    pca=PCA(n_components=num_comp)
    comp_timeseries=pca.fit_transform(mask_timeseries)
    return comp_timeseries, num_comp



def motion_24_params(movpar_csv):
    '''
    motioncorr_24params: Regression of 6 head motion parameters and autoregressive
                            models of motion: 6 head motion parameters, 6 head motion parameters one time
                            point before, and the 12 corresponding squared items (Friston et al., 1996)
    '''
    import numpy as np
    rigid_params=extract_rigid_movpar(movpar_csv)
    movpar=np.zeros([np.size(rigid_params,0), 24])
    movpar[:,:6]=rigid_params
    for i in range(6):
        #add the timepoint 1 TR before
        movpar[0,6+i]=movpar[0,i]
        movpar[1:,6+i]=movpar[:-1,i]
        #add the squared coefficients
        movpar[:,12+i]=movpar[:,i]**2
        movpar[:,18+i]=movpar[:,6+i]**2
    return movpar

def extract_rigid_movpar(movpar_csv):
    import numpy as np
    import csv
    temp = []
    with open(movpar_csv) as csvfile:
        motcorr = csv.reader(csvfile, delimiter=',', quotechar='|')
        for row in motcorr:
            temp.append(row)
    movpar=np.zeros([(len(temp)-1), 6])
    j=0
    for row in temp[1:]:
        for i in range(2,len(row)):
            movpar[j,i-2]=float(row[i])
        j=j+1
    return movpar


def extract_mask_trace(bold, mask):
    import numpy as np
    import nilearn.masking
    mask_signal=nilearn.masking.apply_mask(bold, mask)
    mean_trace=np.mean(mask_signal, 1)
    return mean_trace



def extract_labels(atlas):
    import nilearn.regions
    nilearn.regions.connected_label_regions(atlas)


class MaskEPIInputSpec(BaseInterfaceInputSpec):
    mask = File(exists=True, mandatory=True, desc="Mask to transfer to EPI space.")
    ref_EPI = File(exists=True, mandatory=True, desc="Motion-realigned and SDC-corrected reference 3D EPI.")
    anat_to_EPI_trans = File(exists=True, desc="Transforms for registration of EPI to anat, in order to move the mask to the EPI native space.")
    SyN_SDC = traits.Bool(mandatory=True, desc="If SyN SDC was used, the ref EPI is already overlapping with the anat space, so no transform need to be used.")
    name_spec = traits.Str(desc="Specify the name of the mask.")

class MaskEPIOutputSpec(TraitedSpec):
    EPI_mask = traits.File(desc="The generated EPI mask.")

class MaskEPI(BaseInterface):

    input_spec = MaskEPIInputSpec
    output_spec = MaskEPIOutputSpec

    def _run_interface(self, runtime):
        import os
        import nibabel as nb
        from nipype.interfaces.base import CommandLine

        subject_id=os.path.basename(moving_image).split('_ses-')[0]
        session=os.path.basename(moving_image).split('_ses-')[1][0]
        run=os.path.basename(moving_image).split('_run-')[1][0]
        filename_template = os.path.abspath('%s_ses-%s_run-%s' % (subject_id, session, run))

        resampled_mask_path=os.path.abspath('%s_resampled_mask.nii.gz' % (filename_template))

        if self.inputs.name_spec==None:
            new_mask_path=os.path.abspath('%s_EPI_mask.nii.gz' % (filename_template))
        else:
            new_mask_path=os.path.abspath('%s_%s.nii.gz' % (filename_template, self.inputs.name_spec))

        if self.inputs.SyN_SDC: #no transform is used if SyN SDC was applied
            to_EPI = CommandLine('antsApplyTransforms', args='-i ' + self.inputs.mask + ' -r ' + self.inputs.ref_EPI + ' -o ' + resampled_mask_path + ' -n GenericLabel')
            to_EPI.run()
        else:
            to_EPI = CommandLine('antsApplyTransforms', args='-i ' + self.inputs.mask + ' -r ' + self.inputs.ref_EPI + ' -t ' + self.inputs.EPI_to_anat_trans + ' -o ' + resampled_mask_path + ' -n GenericLabel')
            to_EPI.run()

        nb.Nifti1Image(nb.load(resampled_mask_path).dataobj, nb.load(self.inputs.ref_EPI).affine,
                       nb.load(self.inputs.ref_EPI).header).to_filename(new_mask_path)

        setattr(self, 'EPI_mask', new_mask_path)
        return runtime

    def _list_outputs(self):
        return {'EPI_mask': getattr(self, 'EPI_mask')}
