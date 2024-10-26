import socket
import time
import argparse
import json

# Constants
MSS = 1400  # Maximum Segment Size for each packet
WINDOW_SIZE = 5  # Number of packets in flight
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = "file_to_transfer.txt"  # Change this to the path of the file you want to transfer
TIMEOUT = 1.0  # Initial timeout value, which will be dynamically updated
THROUGHPUT = 50  # in mbps
DEVIATION = 0
ESTIMATED_RTT = 0

def send_file(server_ip, server_port, enable_fast_recovery):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    # Initialize UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    # Wait for client to initiate connection
    client_address = None
    
    #establishing connection
    print("Waiting for client connection...")
    data, client_address = server_socket.recvfrom(1024)
    print(f"Connection established with client {client_address}")
    
    # server_socket.sendto(packet, client_address)  # Send first packet after connection

    initial_rtt = find_rtt_initial(server_socket,client_address)
    TIMEOUT = initial_rtt
    ESTIMATED_RTT = initial_rtt
    ab = THROUGHPUT*initial_rtt*1000*1000
    ab/=8
    ab/=MSS
    WINDOW_SIZE = ab
    
    print(WINDOW_SIZE)
    WINDOW_SIZE = 10
    
    

    with open(FILE_PATH, 'rb') as file:
        seq_num = 0
        window_base = 0
        unacked_packets = {}
        duplicate_ack_count = 0
        last_ack_received = -1
        to_update_rtt = False
        rtt_packet = -1
        end_of_file_send = False

        while True:
            # Send packets within the window
            while seq_num < window_base + WINDOW_SIZE:
                chunk = file.read(MSS)
                if not chunk:
                    if not end_of_file_send:
                        end_of_file_send = True
                        data = b"END_OF_FILE_HERE"
                        packet = {
                        "seq_num": seq_num,
                        "data": data.decode("latin1"),  # Use latin1 to handle binary data in JSON
                        "len_data": len(data)
                        
                        }   
                        # server_socket.sendto(packet, client_address)
                        
                    # End of file
                    break

                # Create and send the packet
                packet = create_packet(seq_num, chunk)
                if not to_update_rtt:
                    rtt_packet = seq_num
                    to_update_rtt = True
                # if client_address:
                server_socket.sendto(packet, client_address)
                print(f"Sent packet {seq_num}")
                # else:
                #     # Wait for client to initiate connection
                #     print("Waiting for client connection...")
                #     data, client_address = server_socket.recvfrom(1024)
                #     print(f"Connection established with client {client_address}")
                #     server_socket.sendto(packet, client_address)  # Send first packet after connection

                # Track sent packets
                unacked_packets[seq_num] = (packet, time.time())
                seq_num += len(chunk)

            # Wait for ACKs and handle retransmissions
            try:
                server_socket.settimeout(TIMEOUT)
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_seq_num = int(ack_packet.decode())
                

                
                
                if ack_seq_num > last_ack_received:
                    print(f"Received cumulative ACK for packet {ack_seq_num}")
                    if ack_seq_num>rtt_packet and to_update_rtt:
                        # print(rtt_packet)
                        # print(unacked_packets)
                        update_rtt(initial=unacked_packets[rtt_packet][1],final=time.time())
                        to_update_rtt = False
                    window_base = handle_ack(ack_seq_num, unacked_packets, last_ack_received)
                    last_ack_received = ack_seq_num
                    # Reset duplicate ACK count
                    duplicate_ack_count = 0
                    
                    

                elif ack_seq_num == last_ack_received:
                    # Duplicate ACK received
                    duplicate_ack_count += 1
                    print(f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_count}")

                    if enable_fast_recovery and duplicate_ack_count >= DUP_ACK_THRESHOLD:
                        print("Entering fast recovery mode")
                        if ack_seq_num==rtt_packet:
                            to_update_rtt = False
                        fast_recovery(server_socket, client_address, unacked_packets)
                        
                

            except socket.timeout:
                # Timeout handling: retransmit all unacknowledged packets
                print("Timeout occurred, retransmitting unacknowledged packets")
                if ack_seq_num==rtt_packet:
                        to_update_rtt = False
                duplicate_ack_count=0
                TIMEOUT*=2
                retransmit_unacked_packets(server_socket, client_address, unacked_packets,fast_recovery)

            # Check if we are done sending the file
            if not chunk and len(unacked_packets) == 0:
                print("File transfer complete")
                break

def create_packet(seq_num, data):
    """
    Create a packet with the sequence number and data.
    """
    packet = {
        "seq_num": seq_num,
        "data": data.hex(),  # Use latin1 to handle binary data in JSON
        "len_data": len(data)
        
        }   
    return json.dumps(packet).encode("utf-8")

def update_rtt(initial,final):
    global DEVIATION,ESTIMATED_RTT,TIMEOUT
    diff = final - initial
    DEVIATION = (0.75*DEVIATION)+(0.25*(abs(diff-ESTIMATED_RTT)))
    ESTIMATED_RTT = (0.875*ESTIMATED_RTT)+(0.125*diff)
    TIMEOUT = ESTIMATED_RTT + (4*DEVIATION)
    
    
    

def find_rtt_initial(server_socket,client_address):
    timeout = 1
    seq = 0
    data = b"RTT_PACKET"
    data = data.ljust(MSS, b'\x00')
    time_dict = {}
    
    while True:
        packet = {
        "seq_num": seq,
        "data": data.hex(),  # Use latin1 to handle binary data in JSON
        "len_data": len(data)
        }
        print("rtt")
        packet = json.dumps(packet).encode("utf-8")
        time_dict[seq]=time.time()
        server_socket.sendto(packet, client_address)
        try:
            server_socket.settimeout(timeout)
            ack_packet, _ = server_socket.recvfrom(1024)
            ack_seq_num = int(ack_packet.decode())
            tim_val = time.time()-time_dict[ack_seq_num-MSS]
            return tim_val
        except socket.timeout:
            timeout*=2
            seq+=MSS
            
        
    
    
def retransmit_unacked_packets(server_socket, client_address, unacked_packets,state):
    """
    Retransmit all unacknowledged packets.
    """
    if not state:
        for seq_num, (packet, _) in unacked_packets.items():
            print(f"Retransmitting packet {seq_num}")
            server_socket.sendto(packet, client_address)  
    else:
        earliest_seq_num = min(unacked_packets.keys())
        packet, _ = unacked_packets[earliest_seq_num]
        print(f"Fast recovery: retransmitting packet {earliest_seq_num}")
        server_socket.sendto(packet, client_address)

def fast_recovery(server_socket, client_address, unacked_packets):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    earliest_seq_num = min(unacked_packets.keys())
    packet, _ = unacked_packets[earliest_seq_num]
    print(f"Fast recovery: retransmitting packet {earliest_seq_num}")
    server_socket.sendto(packet, client_address)

def handle_ack(ack_seq_num, unacked_packets, last_ack_received):
    """
    Update unacked packets and slide the window.
    """
    if ack_seq_num > last_ack_received:
        print(f"Sliding window. ACK received for {ack_seq_num}")
        last_ack_received = ack_seq_num
        # Remove all acknowledged packets from the buffer
        for seq in list(unacked_packets):
            if seq < ack_seq_num:
                del unacked_packets[seq]
    return last_ack_received

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('--fast_recovery', type=bool, default=True, help='Enable fast recovery')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port, args.fast_recovery)
