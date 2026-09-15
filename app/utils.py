import hashlib
import io
import random
import socket
from string import ascii_letters

import requests


from .decoder import decode_dictionary, decode_peers, decode_peer_handshake
from .encoder import calculate_info_hash
from .aliases import MAX_RETRIES, _16KB, MSGID, WaitError

# semi constants
DEFAULT_PORT = 6881
UPLOADED = 0
DOWNLOADED = 0
COMPACT = 1

def open_torrent_file(filename: str) -> dict:
  with open(filename, "rb") as file:
    sample = file.readline()
  tor_dict, _ = decode_dictionary(sample, 1)
  return tor_dict

def recvall(sock: socket.socket, length: int) -> bytes:
  data = b''
  while len(data) < length:
    more = sock.recv(length - len(data))
    if not more:
      raise EOFError(f'Was epecting {length} bytes but only received {len(data)} bytes before the socket closed')
    data += more
  return data

# 165.232.38.164:51433

def generate_random_bytes(length: int):
  result = random.choices(ascii_letters, k=length)
  return "".join(result)

def get_peers(tor_dict: dict, port: int=DEFAULT_PORT, uploaded: int=UPLOADED, downloaded: int=DOWNLOADED, compact: int=COMPACT) -> list[str]:
  tracker_url = tor_dict["announce"].decode(encoding="utf-8")
  left = tor_dict["info"]["length"]
  peer_id: str = generate_random_bytes(20)
  info_hash_url = calculate_info_hash(tor_dict["info"], use_hex=False) # let requests handle url conversion automatically

  response = requests.get(url=tracker_url, params={
    "info_hash": info_hash_url,
    "peer_id": peer_id,
    "port": port,
    "uploaded": uploaded,
    "downloaded": downloaded,
    "left": left,
    "compact": compact
  })

  res_dict = response.content
  res_dict, _ = decode_dictionary(res_dict, 1)
  if "failure_reason" in res_dict:
    raise Exception("An error occurred when checking peers", res_dict["failure_reason"])
  if not "peers" in res_dict:
    raise Exception("An error occured, could not find peers")

  peers = res_dict["peers"]
  return decode_peers(peers)

def perform_handshake(tor_file: str, tor_client: str, close_soc: bool=True) -> socket.socket | None:
  tor_dict = open_torrent_file(tor_file)
  ip_address, port = tor_client.split(':')

  buffer = io.BytesIO()
  proto_len: bytes = int(19).to_bytes(1)
  proto: bytes = str("BitTorrent protocol").encode(encoding="utf-8")
  reserved_bytes = int(8).to_bytes(8)
  info_hash = calculate_info_hash(tor_dict["info"], use_hex=False)
  peer_id: bytes = generate_random_bytes(20).encode(encoding="utf-8")
  recv_len = len(proto_len) + len(proto) + len(reserved_bytes) + len(info_hash) + len(peer_id)

  # write to buffer in specific order
  buffer.write(proto_len)
  buffer.write(proto)
  buffer.write(reserved_bytes)
  buffer.write(info_hash)
  buffer.write(peer_id)

  buffer.seek(0)  

  soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  try:
    soc.connect((ip_address, int(port)))
    soc.sendall(buffer.read())
    reply = recvall(soc, recv_len)
    result = decode_peer_handshake(reply)
    print("Peer ID: ", result["peer_id"].hex())
  except Exception as e:
    print(f"An error occured when connecting to the address: {ip_address}:{port}")
    return
  
  if close_soc:    
    soc.close()
    return
  return soc

def has_piece(s_byte: int, bit_position: int) -> bool:
  """
    5 / 8 -> 0, 5\n
    7 - 5 = 2\n
    7654 3210\n
    1110 0011\n
    0011 1000 & 0000 0001\n
        
    2 / 8 -> 0, 2\n
    7 - 2 = 5\n
    7654 3210\n
    1110 0011\n
    0000 0111 & 0000 0001\n
  """
  shifted = s_byte >> bit_position
  return (shifted & 1) == 1


def download_piece(torr_file, tor_dict: dict, piece_idx: int, peers: list[str], output_file: str) -> None:
  for peer in peers:
    soc: socket.socket | None = perform_handshake(torr_file, peer, close_soc=False)
    if not soc:
      # the error message will be printed by the perform_handshake function already
      continue 
      
    reply = recvall(soc, 5)
    msg_len = int.from_bytes(reply[:4], byteorder="big")
    msg_id = MSGID(reply[4])
    if msg_id != MSGID.BITFIELD:
      # if the peer has partitions, the first message is a bitfield, if not, we move to the next peer.
      _ = recvall(soc, msg_len-1)
      print(f"Peer {peer} does not have partitions!")
      soc.close()
      continue

    bitfield_payload = recvall(soc, msg_len-1)
    byte_idx = piece_idx // 8
    bit_position = 7 - (piece_idx % 8)

    if not has_piece(bitfield_payload[byte_idx], bit_position):
      print(f"Peer {peer} does not have the desired partition!")
      soc.close()
      continue

    # send an interested message
    msg_len = int(1).to_bytes(4, byteorder="big")
    msg_code = MSGID.INTERESTED.to_bytes(1, byteorder="big")
    intrest_msg = msg_len + msg_code
    soc.sendall(intrest_msg)

    # wait for unchoke
    unchoke_tries = 0
    while True:
      reply = recvall(soc, 4)
      msg_len = int.from_bytes(reply)
      payload = recvall(soc, msg_len)
      msg_id = MSGID(payload[0])
      if msg_id == MSGID.UNCHOKE:
        break
      unchoke_tries+=1
      if unchoke_tries > MAX_RETRIES:
        break

    if unchoke_tries > MAX_RETRIES:
      print(f"Waited too long for unchoke request from {peer}!")
      print("Trying another peer!")
      soc.close()
      continue

    # after unchoke, we can start sending requests.
    file_length = tor_dict["info"]["length"]
    piece_length = tor_dict["info"]["piece length"]

    piece_quotient, piece_remainder = divmod(file_length, piece_length)
    # piece_size = piece_length if piece_idx < piece_quotient else piece_remainder
    if (piece_remainder == 0) or piece_idx < piece_quotient:
      piece_size = piece_length
    else:
      piece_size = piece_remainder
    blk_quotient, blk_remainder = divmod(piece_size, _16KB)
    walk = [(0, 0) for _ in range(blk_quotient)]
    if blk_remainder != 0:
      walk.append((0, blk_remainder))
    # create blocks based on quotient and remainders
    begin = 0
    buffer = io.BytesIO()

    for _, rmd in walk:
      # send request msg for each block
      length = _16KB if rmd == 0 else rmd
      msg_id = MSGID.REQUEST.to_bytes(1)
      index = piece_idx.to_bytes(4)
      begin_b = begin.to_bytes(4)
      length_ = length.to_bytes(4)
      payload_len = len(msg_id) + len(index) + len(begin_b) + len(length_)
      payload = payload_len.to_bytes(4) + msg_id + index + begin_b + length_
      begin+=length
          
      soc.sendall(payload)
      block_retries = 0
      while True:
        reply = recvall(soc, 4)
        msg_len = int.from_bytes(reply)
        reply = recvall(soc, msg_len)
        msg_id = MSGID(reply[0])
        if msg_id == MSGID.PIECE:
          payload = reply[1:]
          p_idx = 0
          # skip index and begin
          _ = payload[p_idx:p_idx+4]
          p_idx+=4
          _ = payload[p_idx:p_idx+4]
          p_idx+=4
          block = payload[p_idx:]
          buffer.write(block)
          break
        block_retries+=1
        if block_retries > MAX_RETRIES:
          raise WaitError("Waited too long for a block response from the peer")

    buffer.seek(0)
    contents = buffer.read()
    hash_digest = hashlib.sha1(contents).digest()
    print(len(hash_digest))
    print("downloaded hash", hash_digest)

    start = piece_idx * 20
    end = start+20

    print("tor_hash" ,tor_dict["info"]["pieces"][start:end])
    assert hash_digest == tor_dict["info"]["pieces"][start:end]

    with open(output_file, "ab") as file:
      buffer.seek(0)
      file.write(buffer.read())
      soc.close()
      return

if __name__ == "__main__":
  print(generate_random_bytes(20))