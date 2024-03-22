import logging
from pathlib import Path
from datetime import datetime

from .data.aixm2 import parse_aixm
from .data.kml import KMLParser
from .handlers.plaintext import PlainTextHandler
from .handlers.jinja import JinjaHandler

SUFFIXES = [".txt", ".jinja"]


class Builder:
    def __init__(self, source_dir, target_dir, config):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.config = config

        self.data = {}
        for data_source in config["data"].keys():
            data_source_type = config["data"][data_source]["type"]
            if data_source_type == "aixm":
                logging.debug(f"Loading AIXM source {data_source}...")
                self.data[data_source] = parse_aixm(source_dir / config["data"][data_source]["source"])
            elif data_source_type == "kml":
                logging.debug(f"Loading KML source {data_source}...")
                data_root = None
                if "root" in config["data"][data_source]:
                    data_root = config["data"][data_source]["root"]
                parser = KMLParser(source_dir / config["data"][data_source]["source"], data_root)
                self.data[data_source] = parser.parse()
            elif data_source_type == "raw":
                logging.debug(f"Loading raw source {data_source}...")
                with open(source_dir / config["data"][data_source]["source"], mode="r", encoding="iso-8859-1") as f:
                    self.data[data_source] = f.read()
            else:
                logging.error(f"Unknown data source type for data source {data_source}")

    def build(self):
        for profile in self.config["profiles"].keys():
            self.build_profile(profile)

    def __best_item(self, profile_id, item):
        """Looks for the best file for an item."""
        profile_candidates = [
            profile_id,
            *self.config["profiles"][profile_id]["aliases"],
        ]

        for candidate in profile_candidates:
            for suffix in SUFFIXES:
                candidate_file = item / f"{candidate}{suffix}"
                if candidate_file.is_file():
                    return candidate_file

        return None

    def __handle_item(self, item):
        if item.suffix == ".txt":
            return PlainTextHandler().handle(item)
        elif item.suffix == ".jinja":
            return JinjaHandler().handle(item, self.data)
        else:
            logging.warning(f"No handler for file type {item.suffix} known. Skipping.")
            return None

    def build_profile(self, profile_id: str):
        logging.info(f"Building profile {profile_id}...")

        for map_data in self.config["profiles"][profile_id]["maps"]:
            self.build_profile_map(profile_id, map_data)

    def build_profile_map(self, profile_id: str, map_data: dict):
        map_id = map_data["map"]
        target_file = map_data["target"]
        maps_root = self.source_dir / "maps" / map_id

        if not maps_root.is_dir():
            logging.error("No map directory. Bailing out.")
            return

        header = f"// {map_id} {profile_id}\n// Auto-generated by mapbuilder. Do not edit manually."

        if "timestamp" in map_data and map_data["timestamp"]:
            header = header + f"\n// Generation time: {datetime.now()}"

        profile_contents = [
            header
        ]

        self.build_visitor(profile_id, maps_root, profile_contents)

        profile_content = "\n\n".join(profile_contents)

        with open(self.target_dir / Path(target_file), mode="w", encoding="iso-8859-1") as tgt_file:
            tgt_file.write(profile_content)

        logging.info("complete.")

    def build_visitor(self, profile_id, rootdir, profile_contents):
        # Possibly inefficient, but we do not have a large number of files (hopefully)
        for item in sorted(rootdir.iterdir()):
            logging.debug(f"Processing item {item}")

            # if regular subdirectory
            if item.is_dir() and not item.suffix == ".d":
                self.build_visitor(profile_id, item, profile_contents)
            else:
                # if per-profile content
                if item.is_dir() and item.suffix == ".d":
                    best_item = self.__best_item(profile_id, item)

                    if best_item:
                        item = best_item

                content = self.__handle_item(item)
                if content:
                    profile_contents.append(content)
