from EVT_fitting import*
import scipy as sp
from openmax_utils import compute_distance
import sys
import numpy as np


def computeOpenMaxProbability(openmax_fc8, openmax_score_u, classes=10, channels=1):

    """ Convert the scores in probability value using openmax

    Input:
    ---------------
    openmax_fc8 : modified FC8 layer from Weibull based computation
    openmax_score_u : degree
    Output:
    ---------------
    modified_scores : probability values modified using OpenMax framework,
    by incorporating degree of uncertainity/openness for a given class

    """
    prob_scores, prob_unknowns = [], []
    for channel in range(channels):
        channel_scores, channel_unknowns = [], []
        for category in range(classes):
            channel_scores += [sp.exp(openmax_fc8[channel, category])]

        total_denominator = sp.sum(sp.exp(openmax_fc8[channel, :])) + sp.exp(sp.sum(openmax_score_u[channel, :]))
        if total_denominator is np.inf:
            total_denominator = sys.float_info.max

        prob_scores += [channel_scores / total_denominator]
        prob_unknowns += [sp.exp(sp.sum(openmax_score_u[channel, :])) / total_denominator]

    prob_scores = sp.asarray(prob_scores)
    prob_unknowns = sp.asarray(prob_unknowns)

    scores = sp.mean(prob_scores, axis=0)
    unknowns = sp.mean(prob_unknowns, axis=0)
    modified_scores = scores.tolist() + [unknowns]
    assert len(modified_scores) == (classes + 1)
    return modified_scores


def recalibrate_scores(weibull_model, labellist, imgarr,
                       layer='fc8', alpharank=10, distance_type='eucos', classes=10, channels=1):
    """
    Given FC8 features for an image, list of weibull model for each class,
    re-calibrate scores
    Input:
    ---------------
    weibull_model : pre-computed weibull_model obtained from weibull_tailfitting() function
    labellist : ImageNet 2012 labellist
    imgarr : features for a particular image extracted using caffe architecture

    Output:
    ---------------
    openmax_probab: Probability values for a given class computed using OpenMax
    softmax_probab: Probability values for a given class computed using SoftMax (these
    were precomputed from caffe architecture. Function returns them for the sake
    of convienence)
    """
    if alpharank > len(labellist):
        alpharank = len(labellist)
    imglayer = imgarr[layer]
    ranked_list = np.argsort(imgarr['scores']).ravel()[::-1]
    alpha_weights = [((alpharank + 1) - i) / float(alpharank) for i in range(1, alpharank + 1)]
    ranked_alpha = sp.zeros(1000)
    for i in range(len(alpha_weights)):
        ranked_alpha[ranked_list[i]] = alpha_weights[i]

    # Now recalibrate each fc8 score for each channel and for each class
    # to include probability of unknown
    openmax_fc8, openmax_score_u = [], []
    for channel in range(channels):
        channel_scores = imglayer[channel, :]
        openmax_fc8_channel = []
        openmax_fc8_unknown = []
        count = 0
        for categoryid in range(classes):
            # get distance between current channel and mean vector
            category_weibull = query_weibull(labellist[categoryid], weibull_model, distance_type=distance_type)
            channel_distance = compute_distance(channel_scores, channel, category_weibull[0],
                                                distance_type=distance_type)

            # obtain w_score for the distance and compute probability of the distance
            # being unknown wrt to mean training vector and channel distances for
            # category and channel under consideration
            wscore = category_weibull[2][channel].w_score(channel_distance)
            modified_fc8_score = np.ravel(channel_scores)[categoryid] * (1 - wscore * ranked_alpha[categoryid])
            openmax_fc8_channel += [modified_fc8_score]
            openmax_fc8_unknown += [np.ravel(channel_scores)[categoryid] - modified_fc8_score]

        # gather modified scores fc8 scores for each channel for the given image
        openmax_fc8 += [openmax_fc8_channel]
        openmax_score_u += [openmax_fc8_unknown]
    openmax_fc8 = sp.asarray(openmax_fc8)
    openmax_score_u = sp.asarray(openmax_score_u)

    # Pass the recalibrated fc8 scores for the image into openmax
    openmax_probab = computeOpenMaxProbability(openmax_fc8, openmax_score_u, classes=classes)
    softmax_probab = imgarr['scores'].ravel()
    return sp.asarray(openmax_probab), sp.asarray(softmax_probab)