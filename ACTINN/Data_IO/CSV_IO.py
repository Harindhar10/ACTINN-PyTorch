import sys
import math
import torch
import argparse
import collections
import numpy as np
import scanpy as sc
import pandas as pd
from torch.utils.data import DataLoader

"""
Written based on the original data processing done by ACTINN 
to preserve compatibility with datasets processed by the TF version

"""

def type2label_dict(types):
    
    """
    Turn types into labels
    INPUT: 
        types-> types of cell present in the data
        
    RETURN
     celltype_to_label_dict-> type_to_label dictionary
    
    """
    
    all_celltype = list(set(types))
    celltype_to_label_dict = {}
    
    for i in range(len(all_celltype)):
        celltype_to_label_dict[all_celltype[i]] = i
    return celltype_to_label_dict

def convert_type2label(types, type_to_label_dict):
    
    """ 
    Convert types to labels
    INPUTS:
        types-> list of types
        type_to_label dictionary-> dictionary of cell types mapped to numerical labels
    
    RETURN: 
        labels-> list of labels
    
    """

    types = list(types)
    labels = list()
    for type in types:
        labels.append(type_to_label_dict[type])
    return labels


def scale_sets(sets):
    
    """
    Get common genes, normalize  and scale the sets
    INPUTS: 
        sets-> a list of all the sets to be scaled
    
    RETURN: 
        sets-> normalized sets
    """
    
    common_genes = set(sets[0].index)
    for i in range(1, len(sets)):
        common_genes = set.intersection(set(sets[i].index),common_genes)
    common_genes = sorted(list(common_genes))
    print('len common genes', len(common_genes))
    sep_point = [0]
    for i in range(len(sets)):
        sets[i] = sets[i].loc[common_genes,]
        sep_point.append(sets[i].shape[1])
    total_set = np.array(pd.concat(sets, axis=1, sort=False), dtype=np.float32)
    total_set = np.divide(total_set, np.sum(total_set, axis=0, keepdims=True)) * 20000
    total_set = np.log2(total_set+1)
    expr = np.sum(total_set, axis=1)
    total_set = total_set[np.logical_and(expr >= np.percentile(expr, 1), expr <= np.percentile(expr, 99)),]
    print('total set after expr filtering', total_set.shape)
    
    # Filter out rows with zero mean before calculating CV
    mean_expr = np.mean(total_set, axis=1)
    non_zero_mean_mask = mean_expr > 0
    total_set = total_set[non_zero_mean_mask, :]
    mean_expr = mean_expr[non_zero_mean_mask]
    
    cv = np.std(total_set, axis=1) / np.mean(total_set, axis=1)
    total_set = total_set[np.logical_and(cv >= np.percentile(cv, 1), cv <= np.percentile(cv, 99)),]
    print('total set after cv ', total_set.shape)
    for i in range(len(sets)):
        sets[i] = total_set[:, sum(sep_point[:(i+1)]):sum(sep_point[:(i+2)])]
    return sets


def CSV_IO(train_path:str, train_labels_path:str, test_path:str, test_labels_path:str, 
           batchSize:int =128, workers:int = 12):
    
    """
    This function allows the use of data that was generated by the original ACTINN code (in TF)
    
    INPUTS
        train_path-> path to the h5 file for the training data (dataframe of Genes X Cells)
        train_labels_path-> path to the csv file of the training data labels (cell type strings)
        test_path-> path to the h5 file of the testing data (dataframe of Genes X Cells)
        test_labels_path-> path to the csv file of the testl dataabels (cell type strings)

    RETURN
        train_data_loader-> training data loader consisting of the data (at batch[0]) and labels (at batch[1])
        test_data_loader-> testing data loader consisting of the data (at batch[0]) and labels (at batch[1])
    
    """
    
    
    print("==> Reading in H5 Data frame (CSV)")
    train_set = pd.read_hdf(train_path, key="dge")
    
    train_set = train_set.sample(n=1000, random_state=24, axis=1)
    
    train_set.index = [s.upper() for s in train_set.index]
    train_set = train_set.loc[~train_set.index.duplicated(keep='first')]
    
    test_set = pd.read_hdf(test_path, key="dge")
    
    test_set = test_set.sample(n=1000, random_state=24, axis=1)
    
    print('len testset', len(test_set))
    print(' len trainset', len(train_set))
    test_set.index = [s.upper() for s in test_set.index]
    test_set = test_set.loc[~test_set.index.duplicated(keep='first')]
    
    train_label = pd.read_csv(train_labels_path, header=None, sep="\t")
    
    train_label = train_label.sample(n=1000, random_state=24)
    
    test_label = pd.read_csv(test_labels_path, header=None, sep="\t")
    
    test_label = test_label.sample(n=1000, random_state=24)
    
    barcode = list(test_set.columns)
    nt = len(set(train_label.iloc[:,1]))

    train_set, test_set = scale_sets([train_set, test_set])
    print('len testset', len(test_set))
    print(' len trainset', len(train_set))
    type_to_label_dict = type2label_dict(train_label.iloc[:,1])
    label_to_type_dict = {v: k for k, v in type_to_label_dict.items()}
    print(f"    -> Cell types in training set: {type_to_label_dict}")
    print(f"    -> # trainng cells: {train_label.shape[0]}" )
    
    train_label = convert_type2label(train_label.iloc[:,1], type_to_label_dict)
    test_label =  convert_type2label(test_label.iloc[:,1], type_to_label_dict)
    # we want to get Cells X Genes
    train_set = np.transpose(train_set)
    test_set = np.transpose(test_set)
    print(f"    *** Remember we the data is formatted as Cells X Genes ***" )

    data_and_labels = []
    validation_data_and_labels = [];
    for i in range(len(train_set)):
        # print('len trainset', len(train_label), "len testset", len(test_set))
        data_and_labels.append([train_set[i], train_label[i]])
        
    for i in range(len(test_set)):
        validation_data_and_labels.append([test_set[i], test_label[i]])

    # create DataLoaders
    train_data_loader = DataLoader(data_and_labels, batch_size=batchSize, shuffle=True, sampler=None,
           batch_sampler=None, num_workers=workers, collate_fn=None,
           pin_memory=True)

    test_data_loader = DataLoader(validation_data_and_labels, batch_size=batchSize, shuffle=True, sampler=None,
           batch_sampler=None, num_workers=workers, collate_fn=None,
           pin_memory=True)

    return train_data_loader, test_data_loader, len(type_to_label_dict.keys())
