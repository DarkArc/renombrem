# Copyright 2022 Wyatt Childers
#
# This file is part of renombrem.
#
# renombrem is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# renombrem is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with renombrem.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import os
import taglib
import re
import shutil
import tempfile

from pathlib import Path

def parse_args():
  parser = argparse.ArgumentParser(
    description = 'Rearrange music based on file metadata.'
  )
  parser.add_argument(
    '--verbose',
    dest = 'verbose',
    action = 'store_true',
    help = 'enable verbose mode'
  )
  parser.add_argument(
    '--dry-run',
    dest = 'dry_run',
    action = 'store_true',
    help = 'do a dry run'
  )

  return parser.parse_args()

def get_track_detail(track_data, detail_name):
  if detail_name not in track_data:
    return None

  detail = track_data[detail_name]
  if not isinstance(detail, list):
    return detail

  if len(detail) == 0:
    return None
  return detail[0]

def get_track_artist(track_data):
  album_artist = get_track_detail(track_data, 'ALBUMARTIST')
  if album_artist == None:
    album_artist = get_track_detail(track_data, 'ARTIST')
  return album_artist

def get_track_name(track_data):
  title = get_track_detail(track_data, 'TITLE')
  if title == None:
    return None

  disc_number = get_track_detail(track_data, 'DISCNUMBER')
  if disc_number != None and '/' in disc_number:
    disc_number = disc_number.split('/')[0]
  track_number = get_track_detail(track_data, 'TRACKNUMBER')
  if track_number != None and '/' in track_number:
    track_number = track_number.split('/')[0]

  result = []
  if disc_number != None:
    result.append(disc_number)
  if track_number != None:
    result.append(track_number)
  result.append(title)
  return ' - '.join(result)

SIMPLE_PATH_REGEX = re.compile(r'^[A-Za-z0-9-_ ]+$')

CHAR_REMAPPING = {
  # ->
  ':': '',
  '?': '',
  '\'': '',
  '"': '',
  '#': '',
  # -> -
  '\\': '-',
  '/': '-',
  '*': '-',
  # -> o
  '\u00F8': 'o'
}

def pathify(name):
  if SIMPLE_PATH_REGEX.match(name):
    return name

  chars = []
  for char in name:
    if char in CHAR_REMAPPING:
      chars.append(CHAR_REMAPPING[char])
    else:
      chars.append(char)
  return ''.join(chars)

def _print_confused(cwd, path, artist, album, track_name):
  path_cleaned = str(path).replace(f"{cwd}{os.sep}", '')
  print(f"? {path_cleaned}")
  print(f"    Artist: {artist}")
  print(f"    Album: {album}")
  print(f"    Track: {track_name}")

def _print_move(cwd, from_path, to_path):
  from_path_cleaned = str(from_path).replace(f"{cwd}{os.sep}", '')
  to_path_cleaned = str(to_path).replace(f"{cwd}{os.sep}", '')
  print(f"{from_path_cleaned} -> {to_path_cleaned}")

def _print_delete(cwd, path):
  path_cleaned = str(path).replace(f"{cwd}{os.sep}", '')
  print(f"X {path_cleaned}")

def _print_overwrite_move(cwd, path):
  path_cleaned = str(path).replace(f"{cwd}{os.sep}", '')
  print(f"! Skipping move, {path} exists!")

SUPPORTED_FILE_TYPES = {
  '.flac',
  '.mp3',
  '.m4a',
  '.ogg'
}

def main():
  args = parse_args()
  cwd = os.getcwd()

  pending_renames = []

  for root, _, filenames in os.walk(cwd):
    for filename in filenames:
      file_path = Path(root, filename).resolve()
      if file_path.suffix not in SUPPORTED_FILE_TYPES:
        continue

      track = None
      try:
        track = taglib.File(str(file_path))
        track_data = track.tags

        # Retrieve the data
        artist = get_track_artist(track_data)
        album = get_track_detail(track_data, 'ALBUM')
        track_name = get_track_name(track_data)

        if artist == None or album == None or track_name == None:
          _print_confused(cwd, file_path, artist, album, track_name)
          continue

        # Convert to path friendly versions
        artist = pathify(artist)
        album = pathify(album)
        track_name = pathify(track_name)

        target_path = Path(
          cwd,
          artist,
          album,
          f"{track_name}{file_path.suffix}"
        ).resolve()

        if file_path == target_path:
          continue

        pending_renames.append((file_path, target_path))
      except OSError:
        pass
      finally:
        if track != None:
          track.close()

  if args.verbose:
    for from_path, to_path in pending_renames:
      _print_move(cwd, from_path, to_path)

  if not args.dry_run:
    user_response = input(
      f"{len(pending_renames)} files will be moved. Continue [y/N]: "
    ).lower()
    if user_response != 'y':
      exit(0)

    for from_path, to_path in pending_renames:
      parent_dir = to_path.parent
      os.makedirs(parent_dir, exist_ok = True)
      if os.path.exists(to_path):
        _print_overwrite_move(cwd, to_path)
        continue

      shutil.move(from_path, to_path)

    changes = True
    while changes:
      dirs_to_remove = []
      for root, dirs, filenames in os.walk(cwd):
        if len(dirs) == 0 and len(filenames) == 0:
          dirs_to_remove.append(root)

      changes = len(dirs_to_remove) > 0
      for dir in dirs_to_remove:
        if args.verbose:
          _print_delete(cwd, dir)
        os.rmdir(dir)
