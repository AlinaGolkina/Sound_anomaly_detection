import librosa
import librosa.core
import librosa.feature
import librosa.display
import numpy as np
import pandas as pd
import scipy

import yaml
import logging
import os
import glob

from sklearn import metrics
from pyod.models.iforest import IForest
from pyod.models.knn import KNN
from pyod.models.lof import LOF
from pyod.models.gmm import GMM
from pyod.models.ocsvm import OCSVM
from pyod.utils.data import generate_data
from pyod.utils.data import evaluate_print
from pyod.utils.example import visualize

from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split, StratifiedKFold
from tqdm import tqdm


# stratified dataset split
def StratifiedKF(X, y):
    """
    X - data
    y - labels
    """
    skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=0)
    idx_list = []
    for idx in skf.split(X, y):
        idx_list.append(idx)
        train_idx, test_idx = idx_list[0]
    X_train, X_test, y_train, y_test = X[train_idx], X[test_idx], y[train_idx], y[test_idx]

    return X_train, X_test, y_train, y_test


def mix_data(X_list: list, y_list: list):
    """
    mixed data with stratified split

    X_list : list of different parts of data
    y_list: list of different parts of data labels

    return : train, test and validation samples
    """
    X_all = np.concatenate(X_list)
    y_all = np.concatenate(y_list)
    # отделим Val для итоговой классификации по outlier score
    X, X_val, y, y_val = StratifiedKF(X_all, y_all)
    # отделим еще test для валидации модели
    X_train, X_test, y_train, y_test = StratifiedKF(X, y)

    return X_train, X_test, X_val, y_train, y_test, y_val


# normalize data
def scaling(X_train, X_test, X_val=None):
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    X_val = scaler.transform(X_val)

    return X_train, X_test, X_val

def anomaly_detection(model_name, X_train, X_test, y_train, y_test):

    clf = models[model_name]
    clf.fit(X_train)

    # get the prediction labels and outlier scores of the training data
    y_train_pred = clf.labels_  # binary labels (0: inliers, 1: outliers)
    y_train_scores = clf.decision_scores_  # raw outlier scores

    # get the prediction on the test data
    y_test_pred = clf.predict(X_test)  # outlier labels (0 or 1)
    y_test_scores = clf.decision_function(X_test)  # outlier scores

    # metrics
    accuracy = metrics.accuracy_score(y_test, y_test_pred)
    precision = metrics.precision_score(y_test, y_test_pred)
    recall = metrics.recall_score(y_test, y_test_pred)
    f1_score = metrics.f1_score(y_test, y_test_pred)
    scores = pd.DataFrame(
        [{'Dataset': None, 'Extraction_type': None, 'Model_name': model_name, 'Accuracy': accuracy, 'Precision': precision, 'Recall': recall, 'F1_score': f1_score}])
    # evaluate and print the results
    report = metrics.classification_report(y_test, y_test_pred)
    #print(f'On Test Data:')
    evaluate_print(model_name, y_test, y_test_scores)
    #print(f'\n{report} \n')

    return scores


# Key algorithms, PyOD implementation
def PyOD_classification_report(X_train, X_test, y_train, y_test, dataset=None, extraction_type='aggregate_MFCC', contamination=0.1):
    """
    dataset : str
        'MIMII_DUE'
        'ToyAdm'
    extraction_type : str
        'aggregate_MFCC' - by default
        'amplitude' - original signal, amplitude values timeseries

    """
    models = {'IForest': IForest(behaviour='old',
                                 contamination=contamination,
                                 max_features=max(1,int(X_train.shape[1]//2)),
                                 max_samples='auto',
                                 n_estimators=10,
                                 n_jobs=-1,
                                 random_state=42,
                                 verbose=0),
              'LOF': LOF(contamination=contamination),
              'KNN': KNN(contamination=contamination),
              'GMM': GMM(contamination=contamination),
              'OCSVM': OCSVM(contamination=0.1)
              }

    pyod_models = pd.DataFrame(
        columns={'Dataset', 'Extraction_type', 'Model_name', 'Accuracy', 'Precision', 'Recall', 'F1_score'})
    for model_name, model in models.items():
        if extraction_type == 'amplitude' and model_name in ['KNN', 'GMM']:
            continue

        clf = models[model_name]
        clf.fit(X_train)

        # get the prediction on the test data
        y_test_pred = clf.predict(X_test)  # outlier labels (0 or 1)
        y_test_scores = clf.decision_function(X_test)  # outlier scores

        # metrics
        accuracy = metrics.accuracy_score(y_test, y_test_pred)
        precision = metrics.precision_score(y_test, y_test_pred)
        recall = metrics.recall_score(y_test, y_test_pred)
        f1_score = metrics.f1_score(y_test, y_test_pred)
        scores = pd.DataFrame(
            [{'Dataset': None, 'Extraction_type': None, 'Model_name': model_name, 'Accuracy': accuracy, 'Precision': precision, 'Recall': recall, 'F1_score': f1_score}])
        pyod_models = pyod_models.append(scores)
        pyod_models['Dataset'] = dataset
        pyod_models['Extraction_type'] = extraction_type

    return pyod_models