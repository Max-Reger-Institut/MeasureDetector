# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Bipartite matcher implementation."""

import tensorflow as tf
from scipy.optimize import linear_sum_assignment
import numpy as np

from object_detection.core import matcher


class GreedyBipartiteMatcher(matcher.Matcher):
  """Wraps a Tensorflow greedy bipartite matcher."""

  def __init__(self, use_matmul_gather=False):
    """Constructs a Matcher.

    Args:
      use_matmul_gather: Force constructed match objects to use matrix
        multiplication based gather instead of standard tf.gather.
        (Default: False).
    """
    super(GreedyBipartiteMatcher, self).__init__(
        use_matmul_gather=use_matmul_gather)

  def _match(self, similarity_matrix, valid_rows):
    """Bipartite matches a collection rows and columns. A greedy bi-partite.

    TODO(rathodv): Add num_valid_columns options to match only that many columns
    with all the rows.

    Args:
      similarity_matrix: Float tensor of shape [N, M] with pairwise similarity
        where higher values mean more similar.
      valid_rows: A boolean tensor of shape [N] indicating the rows that are
        valid.

    Returns:
      match_results: int32 tensor of shape [M] with match_results[i]=-1
        meaning that column i is not matched and otherwise that it is matched to
        row match_results[i].
    """
    valid_row_sim_matrix = tf.gather(similarity_matrix,
                                     tf.squeeze(tf.where(valid_rows), axis=-1))
    invalid_row_sim_matrix = tf.gather(
        similarity_matrix,
        tf.squeeze(tf.where(tf.logical_not(valid_rows)), axis=-1))
    similarity_matrix = tf.concat(
        [valid_row_sim_matrix, invalid_row_sim_matrix], axis=0)
    # Convert similarity matrix to distance matrix as tf.image.bipartite tries
    # to find minimum distance matches.
    distance_matrix = -1 * similarity_matrix
    num_valid_rows = tf.reduce_sum(tf.cast(valid_rows, dtype=tf.float32))
    
    def bipartite_matching(distance_matrix):
        row_indices, col_indices = linear_sum_assignment(distance_matrix)
        return row_indices.astype(np.int32), col_indices.astype(np.int32)

    row_indices, col_indices = tf.numpy_function(
        func=bipartite_matching,
        inp=[distance_matrix],
        Tout=[tf.int32, tf.int32]
    )
    
    match_results = tf.fill([tf.shape(similarity_matrix)[1]], -1)
    match_results = tf.tensor_scatter_nd_update(
        match_results,
        tf.expand_dims(col_indices, axis=-1),
        row_indices
    )
    return match_results
