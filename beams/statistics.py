#!/usr/bin/python
# -*- coding: utf-8 -*-

import numpy as np
import scipy.stats
from multiprocessing import Pool, cpu_count
import networkx as nx
import time
import pandas as pd


def _cc_pp_(pairs, method, ncpus):

    coeffs = []

    pool = Pool(cpu_count() - 1 if ncpus is None else ncpus)

    if len(pairs) > ncpus:
        pairs = [pairs[i: i + len(pairs) / ncpus] for i in range(0, len(pairs), len(pairs) / ncpus)]
    else:
        pairs = [pairs]

    if method == "pearson":
        results = pool.map(_pearsonr, pairs)
    elif method == "spearman":
        results = pool.map(_spearmanr, pairs)

    pool.close()
    pool.join()

    for result in results:
        coeffs.extend(result)

    return coeffs


def _pearsonr(pairs):
    temp = []
    for pair in pairs:
        out = scipy.stats.pearsonr(pair[0], pair[1])
        temp.append([out[0], out[1]])
    return temp


def _spearmanr(pairs):
    temp = []
    for pair in pairs:
        out = scipy.stats.spearmanr(pair[0], pair[1])
        temp.append([out[0], out[1]])
    return temp


def correlation_coefficients(df, max_rt_diff=5.0, coeff_thres=0.7, pvalue_thres=0.05, method="pearson", block=5000, ncpus=None):

    if ["name", "mz", "rt"] == list(df.columns.values[0:3]):
        ncols = 4
        df = df.sort_values(['rt', 'mz']).reset_index(drop=True)
    elif "mz" == df.columns.values[0] and "rt" not in df.columns.values:
        ncols = 1
    else:
        raise ValueError("Incorrect column names: [name, mz, rt] or [mz, intensity]")

    if ncpus == None:
        ncpus = cpu_count() - 1

    coefs_pvalues, pairs, peaks = [], [], []
    n = len(df.iloc[:, 0])

    for i in range(n):

        for j in range(i + 1, n):

            if max_rt_diff is not None:
                rt_diff = abs(float(df.loc[j, "rt"] - df.loc[i, "rt"]))
            else:
                rt_diff = 0.0 # Direct Infusion - no retention time available

            if rt_diff < max_rt_diff and max_rt_diff is not None:
                nas = np.logical_or(pd.isnull(df.iloc[i, ncols:-1].values), pd.isnull(df.iloc[j, ncols:-1].values))
                peaks.append([df.iloc[i, 0], df.iloc[j, 0], rt_diff])
                pairs.append([df.iloc[i, ncols:-1].values[~nas], df.iloc[j, ncols:-1].values[~nas]])

            if len(pairs) == block * ncpus:
                print "Calculating correlations for {} pairs (subset)".format(len(pairs))

                coeffs = _cc_pp_(pairs, method, ncpus)
                for k in range(len(coeffs)):
                    if abs(coeffs[k][0]) > coeff_thres and (abs(coeffs[k][1]) < pvalue_thres or pvalue_thres is None):
                        coefs_pvalues.append([peaks[k][0], peaks[k][1], coeffs[k][0], coeffs[k][1], peaks[k][2]])
                pairs, peaks = [], []

            if rt_diff > max_rt_diff:
                break

    print "Calculating correlations for {} pairs (subset)".format(len(pairs))
    coeffs = _cc_pp_(pairs, method, ncpus)
    for k in range(len(coeffs)):
        if coeffs[k][0] > coeff_thres and (coeffs[k][1] < pvalue_thres or pvalue_thres is None):
            coefs_pvalues.append([peaks[k][0], peaks[k][1], coeffs[k][0], coeffs[k][1], peaks[k][2]])
    return coefs_pvalues


def correlation_graphs(coeffs_pvalues, df):
    G = nx.OrderedDiGraph()
    for cp in coeffs_pvalues:
        if "name" == df.columns.values[0]:
            mz_a = float(df.loc[df['name'] == cp[0]].values[0][1]) #mz
            mz_b = float(df.loc[df['name'] == cp[1]].values[0][1]) #mz

            inten_a = float(df.loc[df['name'] == cp[0]].values[0][3]) #intensity
            inten_b = float(df.loc[df['name'] == cp[1]].values[0][3]) #intensity
            G.add_node(cp[0], mz=mz_a, intensity=inten_a)
            G.add_node(cp[1], mz=mz_b, intensity=inten_b)

            if "rt" in df.columns.values:
                G.node[cp[0]]["rt"] = float(df.loc[df['name'] == cp[0]].values[0][2])
                G.node[cp[1]]["rt"] = float(df.loc[df['name'] == cp[1]].values[0][2])
            else:
                G.node[cp[0]]["rt"] = 0.0
                G.node[cp[1]]["rt"] = 0.0

            mz_diff = mz_a - mz_b

            if mz_diff < 0:
                G.add_edge(cp[0], cp[1], rvalue=float(cp[2]), pvalue=float(cp[3]), mzdiff = abs(mz_diff))
                if "rt" in df.columns.values:
                    G[cp[0]][cp[1]]['rtdiff'] = float(cp[4])
                else:
                    G[cp[0]][cp[1]]['rtdiff'] = 0.0
            else:
                G.add_edge(cp[1], cp[0], rvalue=float(cp[2]), pvalue=float(cp[3]), mzdiff = abs(mz_diff))
                if "rt" in df.columns.values:
                    G[cp[1]][cp[0]]['rtdiff'] = float(cp[4])
                else:
                    G[cp[1]][cp[0]]['rtdiff'] = 0.0
        else:
            raise ValueError("Incorrect format")
    return G


# TODO: ADD to tests
def main():

    import in_out

    start = time.time()

    fn_peaklist = "../tests/test_data/variableMetadata.txt"
    fn_matrix = "../tests/test_data/dataMatrix.txt"
    db_out = "../tests/test_data/test.db"

    df = in_out.read_lcms_data(fn_peaklist, fn_matrix)
    df = df[0:50]
    coeffs = correlation_coefficients(df, max_rt_diff=5.0, coeff_thres=0.7, pvalue_thres=None, method="pearson")
    end = time.time()
    print 'Multithreaded %f %i' % (end - start, len(coeffs))

    start = time.time()
    graphs = correlation_graphs(coeffs, db_out)

    end = time.time()
    print 'Graphs %f %i' % (end - start, len(graphs))

if __name__ == "__main__":
    main()