import yaml
import csv
import getpass
from netmiko import ConnectHandler
import re
import logging
from jinja2 import Environment, FileSystemLoader
from time import sleep
from time import strftime
import os

logging.basicConfig(filename="aruba-setupper.log", level=logging.INFO,
                    format="%(asctime)s - %(message)s", datefmt="%H:%M:%S")


def read_params():
    """
    This function is needed to read global parameters that are required for the Jinja template.
    Theses parameters are: pap-user and pap-pass, ikepsk, controller and group
    Among those only the group must be present. Other parameters are optional
    They are stored in a file called global.yml
    """
    with open("global.yml") as f:
        data = yaml.safe_load(f)
    if not (data.get("controller") and data.get("group") and data.get("pap_user")
            and data.get("pap_pass") and data.get("ikepsk")):
        logging.error(f"Missing something of the following: controller, group, pap_user, pap_pass pr ikepsk!")
        exit(1)
    return data


def read_aruba_data():
    """
    This function is needed to read task-custom aruba parameters, that are given in the task.
    These parameters are: inventory number, serial number
    They are stored in a file called arubs.csv
    """
    aps = []
    with open("arubs.csv") as f:
        # logging.info(f.read())
        reader = csv.reader(f, delimiter=';')
        # logging.info(reader)
        for invNum, serNum in reader:
            ap = {
                "name": "",
                "invNum": invNum.strip(),
                "serNum": serNum.strip().upper(),
                "mac": "",
                "index": "",
                "status": "absent",
                "flags": ""
            }
            aps.append(ap)
    return aps


def parse_line(line):
    """
    This function is needed to parse one-liner from database into several variables
    """
    name, group, apType, ipAddr, status, flags, switchAddr, \
        standbyAddr, mac, serNum, *other = re.split(r' {2,}', line)
    ap = {
        "name": name,
        "invNum": "",
        "serNum": serNum,
        "mac": mac,
        "index": "",
        "status": status,
        "flags": flags
    }
    return ap


def find_aruba(aps, candidate):
    """
    This function is needed to find one specific AP in a list of APs given in the task
    """
    for i, v in enumerate(aps):
        logging.info(f"We have: {v['serNum']}, we found: {candidate['serNum']}")
        if v["serNum"] == candidate["serNum"]:
            return i
    return -1


def provision(ap, params):
    """
    This function is needed to generate commands to provision specific AP that is ready
    Those commands will be later passed via netmiko to controller
    """
    env = Environment(loader=FileSystemLoader("./"))
    template = env.get_template("provision-template.txt")
    return template.render(**params, **ap).split("\n")


def report_ap(ap):
    """
    This function logs the AP that was provisioned and checked to file and tells about it to user
    """
    print(f"----\n{ap['invNum']};{ap['serNum']};{ap['mac']};{ap['name']} is provisioned\n"
          f"Plug it off!\n----")
    with open("done.txt", 'a') as f:
        f.write(f"{ap['invNum']};{ap['serNum']};{ap['mac']};{ap['name']}\n")
    with open("to_wiki.txt", 'a') as f:
        f.write(f" {ap['name']} {ap['mac']} \n")


def aruba_setupper():
    """
    Step 1. Read the configs and init files
    """
    logging.info("---- Aruba-setupper has beed initiated! ----")
    if os.path.exists("done.txt"):
        os.remove("done.txt")
    if os.path.exists("to_wiki.txt"):
        os.remove("to_wiki.txt")
    with open("done.txt", 'w') as f:
        pass
    with open("to_wiki.txt", 'w') as f:
        f.write(f" ap mac switch port\n")
        pass
    params = read_params()
    aps = read_aruba_data()
    aps_are_provisioned = False
    start_index = index = params["start_index"] if params.get("start_index") else 1
    aps_count = len(aps)
    aps_to_check = []

    """
    Step 2. We are preparing to enter a loop to look for our access points
    For that purpose we initialise the netmiko params
    """
    host = params["controller"]
    logging.info(f"Controller is {host}")
    user = input(f"User: ")
    passwd = getpass.getpass(f'{user} password for {host}: ')
    controller = {
        "device_type": "aruba_os",
        "host": host,
        "username": user,
        "password": passwd,
        "secret": passwd
    }
    ready_to_provision = []
    cmds = []
    while not aps_are_provisioned:
        """
        First of all we must look for our aps in the default group of the controller
        But for the sake of optimisation we also look for our aps in the target group, 
            to check if they are correctly provisioned
        For the same reason we also push any provision commands that we might have
        """
        with ConnectHandler(**controller) as ssh:
            ssh.enable()
            ssh.send_command("no paging")
            default_aps = ssh.send_command("show ap database long group default status up")
            target_aps = ssh.send_command(f"show ap database long group {params['group']} status up")
            if len(cmds) > 0:
                ssh.send_config_set(cmds)
                cmds.clear()
        """
        Now we look line after line to search info about aps
        """
        lines = default_aps.split("\n")
        i = 0
        while i < len(lines):
            if lines[i].find("AP Database") != -1:
                i += 4
                continue
            if lines[i].find("Flags: ") != -1:
                i += 8
                continue
            if lines[i].strip() == "":
                i += 1
                continue
            if lines[i].find("Port information is available only on 6xx.") != -1:
                i += 1
                continue
            if lines[i].find("Total APs:") != -1:
                i += 1
                continue
            # We found some non-garbage line
            logging.info(f"{i}: {lines[i]}")
            ap = parse_line(lines[i])
            found = find_aruba(aps, ap)
            logging.info(f"That is #{found}")
            # Check is the AP is the one we are looking for
            if found != -1:
                # Found a new AP
                # We need to update it's data and notify user
                if aps[found]["status"] == "absent":
                    aps[found]["mac"] = ap["mac"]
                    aps[found]["status"] = ap["status"]
                    aps[found]["flags"] = ap["flags"]
                    msg = f"Found AP {aps[found]['invNum']};{aps[found]['serNum']};{aps[found]['mac']}!"
                    print(msg)
                    logging.info(msg)
                # Found an existing AP
                # If the new discovered AP is inactive and set up a secure tunnel, it is ready to be provisioned
                if aps[found]["status"] != "Ready to provision":
                    logging.info(f"AP was not counted as ready to be provisioned")
                    if aps[found]["flags"] == "2I":
                        logging.info(f"AP flags are 2I")
                        # We remember it, and notify user
                        ready_to_provision.append(found)
                        aps_to_check.append(found)
                        logging.info(aps_to_check)
                        aps[found]["status"] = "Ready to provision"
                        msg = f"AP {aps[found]['invNum']};{aps[found]['serNum']};{aps[found]['mac']} is " \
                              f"ready to be provisioned"
                        print(msg)
                        logging.info(msg)
                    # It is not ready, keep monitoring its status and flags
                    else:
                        aps[found]["status"] = ap["status"]
                        aps[found]["flags"] = ap["flags"]
            i += 1

        # For those APs that are ready to accept commands, we provision them
        for i in ready_to_provision:
            # Different padding based on the number of access points
            if aps_count + start_index > 99:
                aps[i]["index"] = f"{index:03}"
            else:
                aps[i]["index"] = f"{index:02}"
            # We collect commands for that exact AP
            cmds += provision(aps[i], params)
            # And increment index
            index += 1
        ready_to_provision.clear()

        # Now we look through APs in the target group
        lines = target_aps.split("\n")
        i = 0
        while i < len(lines):
            if lines[i].find("AP Database") != -1:
                i += 4
                continue
            if lines[i].find("Flags: ") != -1:
                i += 8
                continue
            if lines[i].strip() == "":
                i += 1
                continue
            if lines[i].find("Port information is available only on 6xx.") != -1:
                i += 1
                continue
            if lines[i].find("Total APs:") != -1:
                i += 1
                continue
            # Same, found non-garbage line
            logging.info(f"{i}:{lines[i]}")
            ap = parse_line(lines[i])
            found = find_aruba(aps, ap)
            logging.info(f"That is #{found}")
            # Check, if the found AP is new in the target list
            # If it is - it was successfully provisioned, otherwise, it wasn't plugged off
            if found != -1 and aps[found]["status"] != "Done":
                aps[found]["status"] = "Done"
                aps[found]["name"] = ap["name"]
                aps_to_check.remove(found)
                logging.info(aps_to_check)
                report_ap(aps[found])
            i += 1

        # When we have checked all the APs and the next free index is equal to the number of AP, then we're done
        if len(aps_to_check) == 0 and index - start_index == aps_count:
            msg = "Looks like we are done!"
            print(msg)
            logging.info(msg)
            aps_are_provisioned = True
        if not aps_are_provisioned:
            msg = f"{strftime('%H:%M:%S - Cycle is complete, going to sleep for a minute')}"
            print(msg)
            logging.info(msg)
            sleep(60)


if __name__ == "__main__":
    aruba_setupper()
