import socket
import argparse
import json
from collections import OrderedDict

# Constants
FILE_PATH = "received_file.txt"  # The file where received data will be saved

def receive_file(server_ip, server_port):
    """
    Receive a file from the UDP server.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    #client_socket.settimeout(1.0)  # Timeout for receiving packets

    expected_seq_num = 0
    unacked_packets = {}
    server_address = (server_ip, server_port)
    is_rtt_done = False
    rtt_data = b"RTT_PACKET"
    buffer = {}
    end_data = b"END_OF_FILE_HERE"
    started = False
    while True:
        # Send initial request to the server
        # if expected_seq_num == 0:
        #     client_socket.sendto(b"START", (server_ip, server_port))

        # try:
            if not started:
                client_socket.sendto(b"START", server_address)
                started = True
            # Receive packets from the server
            ack_packet, _ = client_socket.recvfrom(5000)
            packet = json.loads(ack_packet.decode("utf-8"))
            seq_num = packet["seq_num"]
            data = bytes.fromhex(packet["data"])
            length = packet["len_data"]
            state = True
            if data ==b"END_OF_FILE_HERE":
                client_socket.sendto(b"END", server_address)
                break
            if not is_rtt_done:
                rtt_data = rtt_data.ljust(length, b'\x00')
                if rtt_data==data:
                    state = False
                    expected_seq_num += length  # Increment expected sequence number
                    client_socket.sendto(str(expected_seq_num).encode(), (server_ip, server_port))
                else:
                    is_rtt_done = True
                    expected_seq_num = 0

            if state:      
                # Check if the packet is in order
                if seq_num == expected_seq_num:
                    print(f"Received packet {seq_num}")
                    # Write data to file
                    
                    
                    with open(FILE_PATH, 'ab') as f:
                        # if data==end_data:
                            
                        f.write(data)
                    # Send ACK for the received packet
                        expected_seq_num += length  # Increment expected sequence number
                        buffer = OrderedDict(sorted(buffer.items()))
                        for seq in list(buffer): 
                            if seq == expected_seq_num:
                                expected_seq_num += buffer[seq][1]
                                f.write(buffer[seq][0])
                                del buffer[seq]
                            
                    client_socket.sendto(str(expected_seq_num).encode(), (server_ip, server_port))
                    
                else:
                    # If out of order, reacknowledge the last received packet
                    buffer[seq_num] = (data,length)
                    client_socket.sendto(str(expected_seq_num).encode(), (server_ip, server_port))

        # except socket.timeout:
        #     print("Timeout occurred, no more packets received.")
        #     break
    client_socket.close()
    print("File transfer complete.")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='UDP File Receiver.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()

# Run the client
receive_file(args.server_ip, args.server_port)
