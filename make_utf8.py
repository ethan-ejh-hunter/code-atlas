#!/usr/bin/python3.13

from importlib.resources import path
from itertools import count
import pathlib
import re
import subprocess
import argparse
import sys
import glob
from typing import List
from multiprocessing import Pool
import itertools
from chardet.universaldetector import UniversalDetector

detector = UniversalDetector()

repo_root_dir: pathlib.Path = pathlib.Path(__file__).parent.absolute()

dirs_to_format: List[str] = ["./source-code"]
extensions_to_format: List[str] = [".c", ".h", ".cpp", ".s", ".S", ".jp", ".txt"]

dirs_to_exclude: List[str] = []



# This function will return all of the directories that do not require formatting according to a given path
# this function supports the use of wildcards
def get_exclude_dirs() -> List[str]:
    dirs_excluded: List[str] = []
    # Iterate through each wildcard directory
    for dir_re in dirs_to_exclude:
        # Create the path as an absolute path
        dir_re: str = repo_root_dir / dir_re

        # Fetch all directories/file paths, add each path to a directory
        for d_re in glob.glob((str(dir_re) + "/" + "**"), recursive=True):
            if not pathlib.Path(d_re).is_dir():
                continue

            dirs_excluded.append(d_re)
    return dirs_excluded


# This function will return all of the directories that require formatting according to a given path
# this function supports the use of wildcards
def get_format_dirs() -> List[str]:
    format_dirs: List[str] = []
    # Iterate through each wildcard directory
    for dir_to_format in dirs_to_format:
        # Create the path as an absolute path
        dir_to_format = repo_root_dir / dir_to_format

        # Fetch all directories/file paths, add each path to a directory
        for d in glob.glob((str(dir_to_format) + "/" + "**"), recursive=True):
            if not pathlib.Path(d).is_dir():
                continue

            format_dirs.append(d)

    return format_dirs

def get_encoding_type(file_path) -> str:
    detector.reset()
    with open(file_path, "rb") as file:
        for line in file:
            detector.feed(line)
    detector.close()
    return detector.result['encoding']

def convertFileWithDetection(file_path, read_encoding):
    lines = []
    with open(file_path, 'rb') as source_file:
        file_content = source_file.read()
    try:
        decoded=file_content.decode("Shift-JIS")
        with open(file_path, "w") as target_file:
            target_file.write(decoded)
        return
    except UnicodeDecodeError:
        pass
    try:
        decoded=file_content.decode("euc_jp")
        with open(file_path, "w") as target_file:
            target_file.write(decoded)
    except UnicodeDecodeError:
        pass




def reencode_directory(directory: str, extensions_to_format: List[str]) -> int:
    """
    formats all files in a directory that have certain extensions

    :param directory: a string containing the path to a directory
    :param extensions_to_format: a list of filename extensions we want to format
    :param only_check: if selected, it will not format the file, only list how many files need formatting
    :returns: an int of how many files were formatted    
    """
    num_formatted: int = 0
    for ext in extensions_to_format:
            for file in pathlib.Path(directory).glob("*" + ext):
                #encoding = get_encoding_type(file)
                encoding = "ShiftJIS"
                convertFileWithDetection(file, encoding)
                num_formatted += 1
            for file in pathlib.Path(directory).glob("Makefile"):
                #encoding = get_encoding_type(file)
                encoding = "ShiftJIS"
                convertFileWithDetection(file, encoding)
                num_formatted += 1
            
    return num_formatted





def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that all files are formatted, and error otherwise.",
    )
    parser.add_argument(
        '-p', '--pool',
        default=6,
        type=int,
        help="How large of a pool to use for formatting files")
    args = parser.parse_args()

    # Get a list of all directories to be formatted and directories that need to be excluded
    # then treat both as sets to take the difference between the formatted directories and
    # excluded directories to obtain directories for formatting.
    dirs_to_format: List[str] = get_format_dirs()
    dirs_excluded: List[str] = get_exclude_dirs()
    dirs_matched: List[str] = list(set(dirs_to_format) - set(dirs_excluded))

    num_formatted: int = 0
    with Pool(args.pool) as pool:
        num_formatted = sum(pool.starmap(reencode_directory, 
                                         zip(dirs_matched, 
                                             itertools.repeat(extensions_to_format, len(dirs_to_format)))))




if __name__ == "__main__":
    main()
