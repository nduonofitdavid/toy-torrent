from typing import Literal
from enum import IntEnum

type Command = Literal ["decode", "info", "peers", "handshake", "download_piece", "download", "magnet_parse", "magnet_handshake", "magnet_info", "magnet_download_piece", "magnet_download"]
MAX_RETRIES = 15
_16KB = 2**14

class MSGID(IntEnum):
  CHOKE=0
  UNCHOKE=1
  INTERESTED=2
  NOT_INTERESTED=3
  HAVE=4
  BITFIELD=5
  REQUEST=6
  PIECE=7
  CANCEL=8

class MSGEXTID(IntEnum):
  REQUEST=0
  DATA=1
  REJECT=2

class WaitError(Exception):
  """This exception is raised when a task takes too long to complete"""
  def __init__(self, message):
    super().__init__(message)
    self.message = message