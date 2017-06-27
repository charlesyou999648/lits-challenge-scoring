from medpy import metric
import numpy as np
from scipy import ndimage

from surface import Surface


def dice(input1, input2):
    return metric.dc(input1, input2)


def detect_lesions(prediction_mask, reference_mask, min_overlap=0.5):
    """
    Produces a mask containing predicted lesions that overlap by at least
    `min_overlap` with the ground truth. The label IDs in the output mask
    match the label IDs of the corresponding lesions in the ground truth.
    
    :param prediction_mask: numpy.array, int or bool
    :param reference_mask: numpy.array, int or bool
    :param min_overlap: float in range [0.5, 1.]
    :return: integer mask (same shape as input masks)
    """
    
    if not min_overlap>0.5 and not min_overlap<=1:
        # An overlap of 0.5 or less would allow a predicted object to "detect"
        # more than one reference object but it would only be mapped to one
        # of those reference objects in this code. The min_overlap determines
        # the open lower bound.
        raise ValueError("min_overlap must be in [0.5, 1.]")
    
    # To reduce computation time, get views into reduced size masks
    bounding_box = ndimage.find_objects(reference_mask>0)[0]
    p = prediction_mask[bounding_box]
    r = reference_mask[bounding_box]
    
    # Get available IDs (excluding 0)
    # 
    # To reduce computation time, check only those lesions in the prediction 
    # that have any overlap with the ground truth.
    p_id_list = np.unique(p[r.nonzero()])[1:]
    g_id_list = np.unique(r)[1:]

    # Produce output mask of detected lesions.
    detected_mask = np.zeros(prediction_mask.shape, dtype=np.uint8)
    for p_id in p_id_list:
        for g_id in g_id_list:
            intersection = np.count_nonzero(np.logical_and(p==p_id, r==g_id))
            union = np.count_nonzero(np.logical_or(p==p_id, r==g_id))
            overlap_fraction = float(intersection)/union
            if overlap_fraction > min_overlap:
                detected_mask[prediction_mask==p_id] = g_id
                
    return detected_mask



def compute_tumor_burden(prediction_mask, reference_mask):
    """
    Calculates the tumor_burden and evalutes the tumor burden metrics RMSE and
    max error.
    
    :param prediction_mask: numpy.array
    :param reference_mask: numpy.array
    :return: dict with RMSE and Max error
    """
    def calc_tumor_burden(vol):
        num_liv_pix=np.count_nonzero(vol>=1)
        num_les_pix=np.count_nonzero(vol==2)
        if num_liv_pix:
            return num_les_pix/float(num_liv_pix)
        return np.inf
    tumor_burden_r = calc_tumor_burden(reference_mask)
    tumor_burden_p = calc_tumor_burden(prediction_mask)

    tumor_burden_diff = tumor_burden_r - tumor_burden_p
    return tumor_burden_diff


def compute_segmentation_scores(prediction_mask, reference_mask,
                                voxel_spacing):
    """
    Calculates metrics scores from numpy arrays and returns an dict.
    
    Assumes that each object in the input mask has an integer label that 
    defines object correspondence between prediction_mask and 
    reference_mask.
    
    :param prediction_mask: numpy.array, int
    :param reference_mask: numpy.array, int
    :param voxel_spacing: list with x,y and z spacing
    :return: dict with dice, jaccard, voe, rvd, assd, rmsd, and msd
    """
    
    scores = {'dice': [],
              'jaccard': [],
              'voe': [],
              'rvd': [],
              'assd': [],
              'rmsd': [],
              'msd': []}
    
    for i, obj_id in enumerate(np.unique(prediction_mask)):
        if obj_id==0:
            continue    # 0 is background, not an object; skip
        import time
        print("DEBUG {}: Processing obj {} of {}"
              " -- shape {}, pred_size {}, ref_size {}"
              "".format(time.time(), i, len(np.unique(prediction_mask))-1,
                        reference_mask.shape,
                        np.count_nonzero(prediction_mask==obj_id),
                        np.count_nonzero(reference_mask==obj_id)))
        # Limit processing to the bounding box containing both the prediction
        # and reference objects.
        target_mask = (reference_mask==obj_id)+(prediction_mask==obj_id)
        bounding_box = ndimage.find_objects(target_mask)[0]
        p = (prediction_mask==obj_id)[bounding_box]
        r = (reference_mask==obj_id)[bounding_box]
        if np.count_nonzero(p) and np.count_nonzero(r):
            dice = metric.dc(p,r)
            jaccard = dice/(2.-dice)
            scores['dice'].append(dice)
            scores['jaccard'].append(jaccard)
            scores['voe'].append(1.-jaccard)
            scores['rvd'].append(metric.ravd(r,p))
            evalsurf = Surface(p, r,
                               physical_voxel_spacing=voxel_spacing,
                               mask_offset=[0.,0.,0.],
                               reference_offset=[0.,0.,0.])
            assd = evalsurf.get_average_symmetric_surface_distance()
            rmsd = evalsurf.get_root_mean_square_symmetric_surface_distance()
            msd = evalsurf.get_maximum_symmetric_surface_distance()
            scores['assd'].append(assd)
            scores['rmsd'].append(rmsd)
            scores['msd'].append(msd)
        else:
            # There are no objects in the prediction, in the reference, or both
            scores['dice'].append(0)
            scores['jaccard'].append(0)
            scores['voe'].append(1.)
            
            # Surface distance (and volume difference) metrics between the two
            # masks are meaningless when any one of the masks is empty. Assign 
            # maximum (infinite) penalty. The average score for these metrics,
            # over all objects, will thus also not be finite as it also loses 
            # meaning.
            scores['rvd'].append(np.inf)
            scores['assd'].append(np.inf)
            scores['rmsd'].append(np.inf)
            scores['msd'].append(np.inf)
              
    return scores
