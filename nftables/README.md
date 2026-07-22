# nftables

Version-controlled firewall policy and deployment helpers.

Current production baseline permits established traffic, loopback, required ICMP/ICMPv6, SSH on `22822/tcp`, and Discrete services on `9330-9332/tcp`; unsolicited input is dropped.
