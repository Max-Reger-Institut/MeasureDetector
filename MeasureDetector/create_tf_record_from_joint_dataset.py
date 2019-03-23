import argparse
import hashlib
import io
import json
import os
import random
from glob import glob

import PIL.Image
import contextlib2
import tensorflow as tf
from typing import List, Dict, Generator

from PIL.Image import Image

from MeasureDetector.create_tf_record_from_individual_json_files import encode_sample_into_tensorflow_sample
from MeasureDetector.errors import InvalidImageFormatError, InvalidImageError, InvalidAnnotationError
from object_detection.dataset_tools import tf_record_creation_util
from object_detection.utils import dataset_util
from object_detection.utils import label_map_util
from tqdm import tqdm

sampling_categories = [
    ("handwritten", "0"),
    ("handwritten", "1"),
    ("handwritten", "2"),
    ("handwritten", "3"),
    ("handwritten", "more"),
    ("typeset", "0"),
    ("typeset", "1"),
    ("typeset", "2"),
    ("typeset", "3"),
    ("typeset", "more"),
]


def annotations_to_tf_example_list(all_image_paths: List[str],
                                   all_annotation_paths: List[str],
                                   label_map_dict: Dict[str, int]) -> Generator[tf.train.Example, None, None]:
    """Convert json files and images to tf.Example proto.

    Notice that this function normalizes the bounding box coordinates provided
    by the raw data.

    Raises:
      ValueError: if the image pointed to by data['filename'] is not a valid JPEG
    """

    total_number_of_images = len(all_image_paths)
    number_of_skipped_or_errored_samples = 0
    error_messages = []
    for index in tqdm(range(total_number_of_images), desc="Serializing annotations", total=total_number_of_images):
        path_to_image, path_to_annotations = all_image_paths[index], all_annotation_paths[index]

        assert (os.path.splitext(os.path.basename(path_to_image))[0] ==
                os.path.splitext(os.path.basename(path_to_annotations))[0])

        try:
            example = encode_sample_into_tensorflow_sample(path_to_image, path_to_annotations, label_map_dict)
            yield example

        except Exception as ex:
            error_messages.append(f"Skipped image {path_to_image} that caused an error: {ex}")
            number_of_skipped_or_errored_samples += 1

    print("Skipped {0} samples".format(number_of_skipped_or_errored_samples))
    for sample in error_messages:
        print(sample)


def main(annotations_directory: str, annotations_filename: str, output_path: str, label_map_path: str,
         number_of_shards: int, target_size: int):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    label_map_dict = label_map_util.get_label_map_dict(label_map_path)
    error_messages = []

    with open(os.path.join(annotations_directory, annotations_filename), 'r') as file:
        dataset = json.load(file)

    with contextlib2.ExitStack() as tf_record_close_stack:
        tf_record = tf_record_creation_util.open_sharded_output_tfrecords(tf_record_close_stack,
                                                                          output_path,
                                                                          number_of_shards)

        for index in tqdm(range(target_size), desc="Serializing annotations", total=target_size):
            current_engraving, number_of_staves = sampling_categories[index % len(sampling_categories)]
            all_items_in_category = dataset[current_engraving][number_of_staves]

            encoding_succeeded = False
            while not encoding_succeeded:
                try:
                    random_sample = random.choice(all_items_in_category)
                    tf_example = encode_sample_into_tensorflow_sample(random_sample["path"], random_sample, label_map_dict)
                    encoding_succeeded = True
                except Exception as ex:
                    error_messages.append(f"Skipped image {random_sample['path']} that caused an error: {ex}")

            shard_index = index % number_of_shards
            tf_record[shard_index].write(tf_example.SerializeToString())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Creates a tensorflow record from an existing dataset. '
                                                 'Balances ')
    parser.add_argument('--annotation_directory', type=str, default="data", help='Directory, where all data is stored')
    parser.add_argument('--annotation_filename', type=str, default="joint_dataset_annotations.json",
                        help='Name of the file containing the annotations')
    parser.add_argument('--output_path', type=str, default="data/output.record",
                        help='Path to output TFRecord')
    parser.add_argument('--label_map_path', type=str, default='mapping.txt',
                        help='Path to label map proto.txt')
    parser.add_argument('--num_shards', type=int, default=4, help='Number of TFRecord shards')
    parser.add_argument('--target_size', type=int, default=5000, help='Number of samples to randomly sample from the'
                                                                      'annotations to be added to the TFRecord.')

    flags = parser.parse_args()
    annotations_directory = flags.annotation_directory
    annotations_filename = flags.annotation_filename
    output_path = flags.output_path
    label_map_path = flags.label_map_path
    number_of_shards = flags.num_shards
    target_size = flags.target_size

    main(annotations_directory, annotations_filename, output_path, label_map_path, number_of_shards, target_size)
