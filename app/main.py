import json
import sys

from .aliases import Command
from .decoder import decode_string, decode_int, decode_list, decode_dictionary
from .encoder import calculate_info_hash, pieces_to_list
from .utils import open_torrent_file, get_peers, perform_handshake, download_piece, parse_magnetlink, magnet_handshake, recvall, magnet_info, download_piece_magnet

def decode_bencode(bencoded_value: bytes):
  sample = bencoded_value

  if not sample:
    raise Exception("Empty bencoded value")

  first = sample[0:1]
  if first.isdigit():
    res, _ = decode_string(sample)
    return res
  elif first == b'i':
    res, _ = decode_int(sample, 1)
    return res  
  elif first == b'l':
    res, _ = decode_list(sample, 1)
    return res
  elif first == b'd':
    res, _ = decode_dictionary(sample, 1)
    return res
  else:
    raise NotImplementedError("Unsupported bencoded type", first)


def main():
  command: Command = sys.argv[1]

  print("Logs from your program will appear here!", file=sys.stderr)

  match command:
    case "decode":
      bencoded_value = sys.argv[2].encode()

      def bytes_to_str(data):
        if isinstance(data, bytes):
          return data.decode()
        raise TypeError(f"Type not serializable: {type(data)}")

      print(json.dumps(decode_bencode(bencoded_value), default=bytes_to_str))
      return

    case "info":
      tor_dict = open_torrent_file(sys.argv[2])
      
      print(f"Tracker URL: {tor_dict["announce"].decode(encoding="utf-8")}")  
      print(f"Length: {tor_dict["info"]["length"]}",)
      print(f"Info Hash: {calculate_info_hash(tor_dict["info"])}",)
      print(f"Piece Length: {tor_dict["info"]["piece length"]}",)
      print("Piece Hashes:")
      print("\n".join(pieces_to_list(tor_dict["info"]["pieces"])))
      return

    case "peers":
      tor_dict = open_torrent_file(sys.argv[2])

      tracker_url = tor_dict["announce"].decode(encoding="utf-8")
      left = tor_dict["info"]["length"]
      info_hash: bytes = calculate_info_hash(tor_dict["info"], use_hex=False)
      peers = get_peers(tracker_url, left, info_hash)
      for peer in peers:
        print(peer)
      return

    case "handshake":
      tor_file = sys.argv[2]
      tor_client = sys.argv[3]
      tor_dict = open_torrent_file(tor_file)
      info_hash = calculate_info_hash(tor_dict["info"], use_hex=False)
      perform_handshake(info_hash_in=info_hash, tor_client=tor_client)
      return

    case "download_piece":
      if (len(sys.argv) < 4) or (len(sys.argv) != 6):
        print("Invalid parameters!")
        return 

      out_filename = None
      if sys.argv[2] == '-o':
        out_filename = sys.argv[3]
        torr_file = sys.argv[4]
        piece_idx = int(sys.argv[5])
      else:
        torr_file = sys.argv[2]
        piece_idx = int(sys.argv[3])

      # fetching piece download requirements
      tor_dict = open_torrent_file(torr_file)
      if not out_filename:
        out_filename = tor_dict["info"]["name"].encode(encoding="utf-8") + f"_piece-{piece_idx}"

      tracker_url = tor_dict["announce"].decode(encoding="utf-8")
      left = tor_dict["info"]["length"]
      info_hash: bytes = calculate_info_hash(tor_dict["info"], use_hex=False)
      peers = get_peers(tracker_url, left, info_hash)
      soc = download_piece(tor_dict["info"], piece_idx, peers, output_file=out_filename)
      if soc:
        soc.close()
      return

    case "download":
      if (len(sys.argv) < 3) or (len(sys.argv) != 5):
        print("Invalid parameters!")
        return 

      out_filename = None
      if sys.argv[2] == '-o':
        out_filename = sys.argv[3]
        torr_file = sys.argv[4]
      else:
        torr_file = sys.argv[2]

      tor_dict = open_torrent_file(torr_file)
      if not out_filename:
        out_filename = tor_dict["info"]["name"].encode(encoding="utf-8")

      tracker_url = tor_dict["announce"].decode(encoding="utf-8")
      left = tor_dict["info"]["length"]
      info_hash: bytes = calculate_info_hash(tor_dict["info"], use_hex=False)
      peers = get_peers(tracker_url, left, info_hash)

      file_length = tor_dict["info"]["length"]
      piece_length = tor_dict["info"]["piece length"]

      piece_quotient, piece_remainder = divmod(file_length, piece_length)
      no_pieces = piece_quotient if piece_remainder == 0 else piece_quotient+1

      for piece_idx in range(no_pieces):
        # print("piece_idx: ", piece_idx)
        download_piece(tor_dict["info"], piece_idx, peers, out_filename)        

      return 

    case "magnet_parse":
      magnet_link = sys.argv[2]
      magnet_dict = parse_magnetlink(magnet_link, verify_tor=True)
      print("Tracker URL:", magnet_dict["tr"])
      print("Info Hash: ", magnet_dict["xt"])
      return

    case "magnet_handshake":
      magnet_link = sys.argv[2]
      magnet_dict = parse_magnetlink(magnet_link, verify_tor=True)
      
      tracker_url = magnet_dict["tr"]
      info_hash = bytes.fromhex(magnet_dict["xt"])
      response = magnet_handshake(tracker_url, info_hash)
      if response:
        soc, _, _ = response
        soc.close()
      return

    case "magnet_info":
      magnet_link = sys.argv[2]
      response = magnet_info(magnet_link)
      if response:
        soc, _, _ = response
        soc.close()
      return

    case "magnet_download_piece":
      if (len(sys.argv) < 4) or (len(sys.argv) != 6):
        print("Invalid parameters!")
        return 

      out_filename = None
      if sys.argv[2] == '-o':
        out_filename = sys.argv[3]
        magnet_link = sys.argv[4]
        piece_idx = int(sys.argv[5])
      else:
        magnet_link = sys.argv[2]
        piece_idx = int(sys.argv[3])

      magnet_dict = parse_magnetlink(magnet_link, verify_tor=True)
      response = magnet_info(magnet_link, debug=False, piece_idx=piece_idx)

      if not response:
        print("An error occured when communicating with peers")
        return
          
      soc, meta_dict, peer_ret = response
      print(peer_ret)
      outfile = out_filename
      if outfile is None:
        outfile = meta_dict["name"].encode(encoding="utf-8") + f"piece-{piece_idx}"

      download_piece_magnet(soc=soc, info_dict=meta_dict, piece_idx=piece_idx, output_filename=outfile, magnet_dict=magnet_dict, peer_ret=peer_ret)
      return

    case "magnet_download":
      if (len(sys.argv) < 3) or (len(sys.argv) != 5):
        print("Invalid parameters!")
        return 

      out_filename = None
      if sys.argv[2] == '-o':
        out_filename = sys.argv[3]
        magnet_link = sys.argv[4]
      else:
        magnet_link = sys.argv[2]

      magnet_dict = parse_magnetlink(magnet_link, verify_tor=True)
      response = magnet_info(magnet_link, debug=False, piece_idx=0)

      if not response:
        print("An error occured when communicating with peers")
        return
          
      soc, meta_dict, peer_ret = response

      if out_filename is None:
        out_filename = meta_dict["name"].encode(encoding="utf-8")

      # download the first piece
      download_piece_magnet(soc=soc, info_dict=meta_dict, piece_idx=0, output_filename=out_filename, magnet_dict=magnet_dict, peer_ret=peer_ret)

      # calculate the size of the other pieces and download them
      file_length = meta_dict["length"]
      piece_length = meta_dict["piece length"]
      # print(meta_dict["name"])

      piece_quotient, piece_remainder = divmod(file_length, piece_length)
      no_pieces = piece_quotient if piece_remainder == 0 else piece_quotient+1
      peers = get_peers(magnet_dict["tr"], left=999, info_hash_url=bytes.fromhex(magnet_dict["xt"]))

      for piece_idx in range(1, no_pieces):
        download_piece(meta_dict, piece_idx, peers, out_filename)        
      return 

    case _:
      raise NotImplementedError(f"Unknown command {command}")

if __name__ == "__main__":
  main()