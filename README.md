# aruba-setupper
This script is required for automatic provision of Aruba APs for the certain group after they are reset to factory defaults

# Required files 

1. List of APs that we're looking for, provided in 'arubs.csv' file with the following syntax:

```
00000XXX;AL0000000
00000YYY;AL1111111
00000ZZZ;AL2387463
```

Where the first number is inventory number and the second one is the serial number of the AP

2. Parameters for the provisioning, provided in 'global.yml' file with the following syntax:

```
group: example
pap_user: puser
pap_pass: ppass
ikepsk: !qwerty123
controller: 10.10.100.25
start_index: 42
```

'start_index' parameter is optional. In case of absence start index will be 0. 
Other parameters must corespond with controller settings. There must be specified group and user\pass for the APs

# Usage

After providing required data launch main.py, enter credentials, user and password.  
During it's workcycle it will report which APs were found from the list, which are about to be provisioned and which are done and may be plugged off
After the script has finished, you'll get file 'done.txt', which, in case of success, will include

```
00000ZZZ;AL2387463;d8:c7:c8:de:ad:bf;ap-name-01
```

It includes previously specified inventory and serial numbers, mac address of AP and it's name

There will also be the 'to_wiki.txt' file, which will include

```
 ap mac switch port
 ap-roshchin-07 00:24:6c:c3:5a:f5
 ap-roshchin-08 24:de:c6:c3:35:2a
```

That information may be directly posted to MediaWiki to create a table
