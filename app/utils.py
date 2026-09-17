import hashlib
import io
import random
import socket
from string import ascii_letters
from urllib.parse import unquote

import requests

from .decoder import decode_dictionary, decode_peers, decode_peer_handshake
from .encoder import calculate_info_hash, bencode_dictionary, pieces_to_list
from .aliases import MAX_RETRIES, _16KB, MSGID, MSGEXTID, WaitError

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

def get_peers(tracker_url: str, left: int, info_hash_url: bytes, port: int=DEFAULT_PORT, uploaded: int=UPLOADED, downloaded: int=DOWNLOADED, compact: int=COMPACT) -> list[str]:
  # tracker_url = tor_dict["announce"].decode(encoding="utf-8")
  # left = tor_dict["info"]["length"]
  peer_id: str = generate_random_bytes(20)
  # info_hash_url = calculate_info_hash(tor_dict["info"], use_hex=False) # let requests handle url conversion automatically

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

def perform_handshake(info_hash_in: bytes, tor_client: str, reserved_bytes_val: int=0, verify_extension: bool=False, close_soc: bool=True, debug:bool=True) -> socket.socket | None:
  ip_address, port = tor_client.split(':')

  buffer = io.BytesIO()
  proto_len: bytes = int(19).to_bytes(1)
  proto: bytes = str("BitTorrent protocol").encode(encoding="utf-8")
  reserved_bytes = reserved_bytes_val.to_bytes(8)
  info_hash = info_hash_in
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
    if verify_extension:
      r_bytes = result["reserved_bytes"]
      if r_bytes[-3] != 16:
        return None
    if debug:
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

def download_piece_sub(soc: socket.socket, info_dict: dict, piece_idx: int, output_file: str) -> int: 
  reply = recvall(soc, 5)
  msg_len = int.from_bytes(reply[:4], byteorder="big")
  msg_id = MSGID(reply[4])
  if msg_id != MSGID.BITFIELD:
    print("inside here")
    # if the peer has partitions, the first message is a bitfield, if not, we move to the next peer.
    _ = recvall(soc, msg_len-1)
    print(f"Peer does not have partitions!")
    soc.close()
    return 1

  bitfield_payload = recvall(soc, msg_len-1)
  byte_idx = piece_idx // 8
  bit_position = 7 - (piece_idx % 8)

  if not has_piece(bitfield_payload[byte_idx], bit_position):
    print(f"Peer does not have the desired partition!")
    soc.close()
    return 1

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
    print(f"Waited too long for unchoke request from peer!")
    print("Trying another peer!")
    soc.close()
    return 1

  # after unchoke, we can start sending requests.
  file_length = info_dict["length"]
  piece_length = info_dict["piece length"]

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

  print("tor_hash" ,info_dict["pieces"][start:end])
  assert hash_digest == info_dict["pieces"][start:end]

  with open(output_file, "ab") as file:
    buffer.seek(0)
    file.write(buffer.read())
    soc.close()
    return 0



def download_piece(info_dict: dict, piece_idx: int, peers: list[str], output_file: str) -> None:
  info_hash = calculate_info_hash(info_dict, use_hex=False)
  assert(isinstance(info_hash, bytes))
  for peer in peers:
    soc: socket.socket | None = perform_handshake(info_hash, peer, close_soc=False)
    if not soc:
      # the error message will be printed by the perform_handshake function already
      continue 

    res = download_piece_sub(soc=soc, info_dict=info_dict, piece_idx=piece_idx, output_file=output_file)      
    if res == 1:
      continue
    else:
      break

#magnet:?xt=urn:btih:ad42ce8109f54c99613ce38f9b4d87e70f24a165&dn=magnet1.gif&tr=http%3A%2F%2Fbittorrent-test-tracker.codecrafters.io%2Fannounce
def parse_magnetlink(link: str, verify_tor=False):
  keys = {}
  skip = 8
  if link[:skip] != "magnet:?":
    raise Exception("Invalid magnet link")

  def add_val(dict, key, val):
    val = unquote(val)
    if key in dict:
      store = dict[key]
      if isinstance(store, list):
        dict[key].append(val)
      else:
        dict[key] = [dict[key], val]
    else:
      dict[key] = val
  
  start = skip
  end = start+1
  key_ = None
  while end < (len(link)):
    curr = link[end]
    if curr == "=":
      key_ = link[start:end]
      start=end+1
      end+=1
      continue
    elif curr == "&":
      if key_:
        add_val(keys, key_, link[start:end])
        start=end+1
        end+=1
        continue
      else:
        raise Exception("The magnet link is malformed")

    end+=1
    if end == len(link):
      if key_:
        add_val(keys, key_, link[start:end])
        continue
      raise Exception("The magnet link is malformed")

  # verifying xt
  if "xt" not in keys:
    raise Exception("The xt query parameter was not found in the magnet link")

  if verify_tor:
    if not "tr" in keys:
      raise Exception("The magnet link does not contain a tracker url")
    v = keys["xt"]
    if v[:9] != "urn:btih:":
      raise Exception("The magnet link provided is not a bittorrent magnet link")
    keys["xt"] = v[9:]

  return keys

def magnet_handshake(tracker_url: str, info_hash: bytes, debug:bool=True) -> tuple[socket.socket, dict] | None:
  left = 999 # dummy placeholder value since length of file is not known
  peers = get_peers(tracker_url, left, info_hash)
  reserved_bytes = 2**20
  for peer in peers:
    soc = perform_handshake(info_hash, peer, reserved_bytes_val=reserved_bytes, close_soc=False, verify_extension=True, debug=False)
    if soc:
      reply = recvall(soc, 4)
      msg_len = int.from_bytes(reply)
      payload = recvall(soc, msg_len)
      msg_id = MSGID(payload[0])
      if msg_id != MSGID.BITFIELD:
        print(f"Peer {peer} does not have partitions!")
        soc.close()
        continue

      # construct extension handshake message
      pay_msg_id = int(20).to_bytes(1)
      ext_msg_id = int(0).to_bytes(1)
      payload_bdict = {"m": {"ut_metadata": 1}}
      payload_bdict = bencode_dictionary(payload_bdict).encode(encoding="utf-8")
      payload = ext_msg_id + payload_bdict
      payload_size = len(payload)
      msg_size = (len(pay_msg_id) + payload_size).to_bytes(4)
      msg = msg_size + pay_msg_id + payload
      soc.sendall(msg)

      # receive extension handshake message
      # the extension handshake message will be of the same structure as the one we sent out
      recv_ext_msg_retries = 0
      r_payload = None
      while True:
        r_reply = recvall(soc, 4)
        r_msg_len =  int.from_bytes(r_reply)
        r_payload = recvall(soc, r_msg_len)
        msg_id = r_payload[0]
        if msg_id == 20:
          break
        recv_ext_msg_retries+=1
        if recv_ext_msg_retries > MAX_RETRIES:
          break

      if recv_ext_msg_retries > MAX_RETRIES:
        print("Waited too long for extension handshake message from peer, trying another peer!") 
        continue

      # if we reach this position, we received an extension handshake message
      r_payload = r_payload[1:]
      ext_msg_id = r_payload[0]
      assert ext_msg_id == 0
      b_dict, _ = decode_dictionary(r_payload[1:], 1)

      if "m" in b_dict:
        peer_meta = b_dict["m"]
        if "ut_metadata" in peer_meta:
          if debug:
            print("Peer Metadata Extension ID: ", peer_meta["ut_metadata"])
          return soc, b_dict
        else:
          raise Exception("Extension format not ut_metadata not provided")
      else:
        raise Exception("Malformed response, the key 'm' was not found")

def magnet_info(magnet_link: str, debug=True) -> tuple[socket.socket, dict] | None:
  magnet_dict = parse_magnetlink(magnet_link, verify_tor=True)
  tracker_url = magnet_dict["tr"]
  info_hash = bytes.fromhex(magnet_dict["xt"])
  response = magnet_handshake(tracker_url, info_hash, debug=False)
  if not response:
    print("Could not establish reliable connection!")
    return
  soc, b_dict = response

  # the next step is to send an extension request message
  peer_metadata_ext_id = int(b_dict["m"]["ut_metadata"]).to_bytes(1)
  msg_id = int(20).to_bytes(1)
  # for this challenge we would assume the metadata would be in only one piece
  msg_bdict = bencode_dictionary({'msg_type': MSGEXTID.REQUEST, 'piece': 0}).encode(encoding="utf-8")
  payload = peer_metadata_ext_id + msg_bdict
  msg = msg_id + payload
  msg_len = len(msg)
  msg_whole = int.to_bytes(msg_len, 4) + msg

  soc.sendall(msg_whole)

  # receive the response
  recv_ext_msg_retires = 0
  r_payload = None
  while True:
    reply = recvall(soc, 4)
    r_msg_len = int.from_bytes(reply)
    r_payload = recvall(soc, r_msg_len)
    msg_id = r_payload[0]
    if msg_id == 20:
      break
    recv_ext_msg_retires+=1
    if recv_ext_msg_retires > MAX_RETRIES:
      break

  if recv_ext_msg_retires > MAX_RETRIES:
    raise WaitError("Waited too long for extension message response from peer!")

  r_payload = r_payload[1:]
  ext_msg_id = r_payload[0]
  assert ext_msg_id == int(b_dict["m"]["ut_metadata"])
  r_payload = r_payload[1:]
  ext_b_dict, idx = decode_dictionary(r_payload, 1)
  metad_dict, _ = decode_dictionary(r_payload[idx:], 1)
  assert info_hash.hex() == calculate_info_hash(metad_dict, use_hex=True)

  if debug:
    print("Tracker URL: ", tracker_url)
    print("Length: ", metad_dict["length"])
    print("Info Hash: ", info_hash.hex())
    print("Piece Length: ", metad_dict["piece length"])
    print("Pieces Hashes:")
    for piece in pieces_to_list(metad_dict["pieces"]):
      print(piece)

  return soc, metad_dict

def download_piece_magnet(soc: socket.socket, piece_idx: int, info_dict: dict, output_filename: str):
  res = download_piece_sub(soc=soc, info_dict=info_dict, piece_idx=piece_idx, output_file=output_filename)
  if res == 1:
    raise Exception("An error occured while downloading the piece")
  


if __name__ == "__main__":
  print(generate_random_bytes(20))
  print(parse_magnetlink("magnet:?xt=urn:btih:ad42ce8109f54c99613ce38f9b4d87e70f24a165&dn=magnet1.gif&tr=http%3A%2F%2Fbittorrent-test-tracker.codecrafters.io%2Fannounce"))
  print(parse_magnetlink("magnet:?xt=1&"))
  print(parse_magnetlink("magnet:?xt=urn:btih:ad42ce8109f54c99613ce38f9b4d87e70f24a165"))

