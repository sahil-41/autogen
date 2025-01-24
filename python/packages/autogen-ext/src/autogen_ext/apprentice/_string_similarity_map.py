import os
import pickle
from typing import Optional, Union, Dict, List, Tuple

import chromadb
from chromadb.config import Settings

from .page_logger import PageLogger


class StringSimilarityMap:
    """
    Provides storage and similarity-based retrieval of string pairs using a vector database.
    Each DB entry is a pair of strings: an input string and an output string.
    The input string is embedded and used as the retrieval key.
    The output string can be anything, but it's typically used as a dict key.
    Vector embeddings are currently supplied by Chroma's default Sentence Transformers.

    Args:
        - settings: The settings for the string similarity map.
        - reset: True to clear the DB immediately after creation.
        - path_to_db_dir: Path to the directory where the DB is stored.
        - logger: The PageLogger object to use for logging.

    Methods:
        - add_input_output_pair: Adds one input-output string pair to the DB.
        - get_related_string_pairs: Retrieves up to n string pairs related to the given query text within the specified distance threshold.
        - reset_db: Forces immediate deletion of the DB's contents, in memory and on disk.
        - save_string_pairs: Saves the string-pair dict to disk.
    """
    def __init__(self, settings: Dict, reset: bool, path_to_db_dir: str, logger: PageLogger) -> None:
        self.settings = settings
        self.logger = logger
        self.verbose = self.settings["verbose"]
        self.path_to_db_dir = path_to_db_dir

        # Load or create the vector DB on disk.
        chromadb_settings = Settings(
            anonymized_telemetry=False, allow_reset=True, is_persistent=True, persist_directory=path_to_db_dir
        )
        self.db_client = chromadb.Client(chromadb_settings)
        self.vec_db = self.db_client.create_collection("string-pairs", get_or_create=True)  # The collection is the DB.

        # Load or create the associated string-pair dict on disk.
        self.path_to_dict = os.path.join(path_to_db_dir, "uid_text_dict.pkl")
        self.uid_text_dict = {}
        self.last_string_pair_id = 0
        if (not reset) and os.path.exists(self.path_to_dict):
            if self.verbose:
                self.logger.info("\nLOADING STRING SIMILARITY MAP FROM DISK  {}".format(self.path_to_dict))
                self.logger.info("    Location = {}".format(self.path_to_dict))
            with open(self.path_to_dict, "rb") as f:
                self.uid_text_dict = pickle.load(f)
                self.last_string_pair_id = len(self.uid_text_dict)
                if self.verbose and len(self.uid_text_dict) > 0:
                    self.logger.info("\n{} STRING PAIRS LOADED".format(len(self.uid_text_dict)))
                    self._log_string_pairs()

        # Clear the DB if requested.
        if reset:
            self.reset_db()

    def _log_string_pairs(self) -> None:
        """
        Logs all string pairs currently in the map.
        """
        self.logger.info("LIST OF STRING PAIRS")
        for uid, text in self.uid_text_dict.items():
            input_text, output_text = text
            self.logger.info("  ID: {}\n    INPUT TEXT: {}\n    OUTPUT TEXT: {}".format(uid, input_text, output_text))

    def save_string_pairs(self) -> None:
        """
        Saves the string-pair dict (self.uid_text_dict) to disk.
        """
        with open(self.path_to_dict, "wb") as file:
            pickle.dump(self.uid_text_dict, file)

    def reset_db(self) -> None:
        """
        Forces immediate deletion of the DB's contents, in memory and on disk.
        """
        if self.verbose:
            self.logger.info("\nCLEARING STRING-PAIR MAP")
        self.db_client.delete_collection("string-pairs")
        self.vec_db = self.db_client.create_collection("string-pairs")
        self.uid_text_dict = {}
        self.save_string_pairs()

    def add_input_output_pair(self, input_text: str, output_text: str) -> None:
        """
        Adds one input-output string pair to the DB.
        """
        self.last_string_pair_id += 1
        self.vec_db.add(documents=[input_text], ids=[str(self.last_string_pair_id)])
        self.uid_text_dict[str(self.last_string_pair_id)] = input_text, output_text
        if self.verbose:
            self.logger.info(
                "\nINPUT-OUTPUT PAIR ADDED TO VECTOR DATABASE:\n  ID\n    {}\n  INPUT\n    {}\n  OUTPUT\n    {}\n".format(
                    self.last_string_pair_id, input_text, output_text
                )
            )
            self._log_string_pairs()

    def get_related_string_pairs(self, query_text: str, n_results: int, threshold: Union[int, float]) -> List[Tuple[str, str, float]]:
        """
        Retrieves up to n string pairs that are related to the given query text within the specified distance threshold.
        """
        if n_results > len(self.uid_text_dict):
            n_results = len(self.uid_text_dict)
        if n_results > 0:
            results = self.vec_db.query(query_texts=[query_text], n_results=n_results)
            num_results = len(results["ids"][0])
        else:
            results = []
            num_results = 0
        string_pairs = []
        for i in range(num_results):
            uid, input_text, distance = results["ids"][0][i], results["documents"][0][i], results["distances"][0][i]
            if distance < threshold:
                input_text_2, output_text = self.uid_text_dict[uid]
                assert input_text == input_text_2
                if self.verbose:
                    self.logger.info(
                        "\nINPUT-OUTPUT PAIR RETRIEVED FROM VECTOR DATABASE:\n  INPUT1\n    {}\n  OUTPUT\n    {}\n  DISTANCE\n    {}".format(
                            input_text, output_text, distance
                        )
                    )
                string_pairs.append((input_text, output_text, distance))
        return string_pairs
