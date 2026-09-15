"""
d7:meaningi42e4:wiki7:bencodee
i24e
7:water
l5:wateri47ee

should we check if an item is a digit, we find the nearest colon
but what if we are sending the string water23:5water

d8:announce31:http://tracker.example/announce4:infod6:length6:1234564:name8:file.txt11:piecelength5:163846:pieces20:12345678901234567890ee

"""
# if every thing is encoded using 4 byte to represent things

def decode_int(sample: bytes, start: int=0,) -> tuple[int, int]:
  end_idx = sample.find(b"e", start)
  if end_idx == -1:
    raise Exception("Error decoding the bencoded integer")
  try:
    integer = int(sample[start:end_idx])
    return integer, end_idx+1
  except Exception:
    raise Exception("Error decoding the bencoded integer", sample[start:end_idx])

def decode_list(sample: bytes, start: int=0) -> tuple[list, int]:
  dec_list = []
  idx = start
  while idx < len(sample):
    current = sample[idx:idx+1]
    if current.isdigit():
      res, idx = decode_string(sample, idx)
      dec_list.append(res)
    elif current == b"d":
      res, idx = decode_dictionary(sample, idx+1)
      dec_list.append(res)
    elif current == b"l":
      res, idx = decode_list(sample, idx+1)
      dec_list.append(res)
    elif current == b"i":
      res, idx = decode_int(sample, idx+1)
      dec_list.append(res)
    elif current == b"e":
      return dec_list, idx+1
    else:
      raise Exception("Unexpected character while decoding bencoded list", current)
  raise Exception("The bencoded list was not terminated")

def decode_string(sample: bytes, start: int=0) -> tuple[bytes, int]:
  stp_point = sample.find(b":", start)
  if stp_point == -1:
    raise Exception("An error occured when decoding bencoded string")
  try:
    str_len = int(sample[start:stp_point])
  except ValueError as e:
    raise Exception("An error occured when decoding bencoded string", e) 
  if str_len < 0:
    raise Exception("Bencoded string length cannot be negative")
  
  v = stp_point+1
  k = v+str_len

  if k > len(sample):
    raise Exception("String length exceeds available data")

  res = sample[v:k]
  return res, k
  
def decode_dictionary(sample: bytes, start=0) -> tuple[dict, int]:
  dec_dict = {}

  if start >= len(sample):
    raise Exception("Unterminated bencoded dictionary")

  if sample[start] == 'e':
    return dec_dict, start+1
  
  key_bytes, idx = decode_string(sample, start)
  key = key_bytes.decode(encoding="utf-8")
  in_key = True

  while idx < len(sample):
    current = sample[idx:idx+1]
    if current.isdigit():
      res, idx = decode_string(sample, idx)
      if in_key:
        dec_dict[key] = res
        in_key = False
      else:
        key = res.decode(encoding="utf-8")
        in_key = True

    elif current == b'i':
      res, idx = decode_int(sample, idx+1)
      if not in_key:
        Exception("The keys of bencoded dicts must always be strings")
      dec_dict[key] = res
      in_key = False

    elif current == b'l':
      res, idx = decode_list(sample, idx+1)
      if not in_key:
        raise Exception("The keys of bencoded dicts must always be strings")
      dec_dict[key] = res
      in_key = False
        
    elif current == b'd':
      res, idx = decode_dictionary(sample, idx+1)
      if not in_key:
        raise Exception("The keys of bencoded dicts must always be strings")
      dec_dict[key] = res
      in_key = False
        
    elif current == b'e':
      return dec_dict, idx+1

    else:
      raise Exception("Unexpected character encountered while decoding bencoded dict", current)
  raise Exception("Bencoded dict not terminated")

def decode_peers(sample: bytes) -> list[str]:
  res: list[str] = []
  idx = 0

  # using compact representation, the first 4 bytes is the ip, the remaining 2 bytes is the port
  while idx < len(sample):
    ip = sample[idx:idx+4]
    idx+=4
    port = int.from_bytes(sample[idx:idx+2], byteorder="big")
    idx+=2
    
    # we are using compact representation, where the first 4 bytes represent the ip address of the peer
    ip_str = f"{ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}:{port}"
    res.append(ip_str)
  
  return res

def decode_peer_handshake(sample: bytes):
  """Decode the response of a peer after establishing a TCP handshake with it using the Bit torrent peer protocol"""
  result = {}

  idx = 0
  proto_len = int.from_bytes(sample[idx:idx+1], byteorder="big")
  idx+=1
  proto = sample[idx:proto_len+1].decode(encoding="utf-8")
  idx+=proto_len
  reserved_bytes = sample[idx:idx+8]
  idx+=8
  sha_hash = sample[idx:idx+20]
  idx+=20
  peer_id = sample[idx:idx+20]
  idx+=20

  assert len(sample) == idx

  result["proto_len"] = proto_len
  result["proto"] = proto
  result["reserved_bytes"] = reserved_bytes
  result["sha_hash"] = sha_hash
  result["peer_id"] = peer_id

  return result  