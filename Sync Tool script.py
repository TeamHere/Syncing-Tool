#!/usr/bin/env python

import time
import telnetlib
import re
import sys
import subprocess
import readline
import os
import getpass
import threading
import logging

from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from colorama import init, deinit, Fore, Style
from sqlalchemy import func
from sqlalchemy import create_engine

logger = logging.getLogger('sqlalchemy.engine')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('sample.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

os.system('cls' if os.name == 'nt' else 'clear')

#Overview of the script and its functions

print """
\nThe following script synching a local database using sqlalchemy ORM with a Cisco machine (Switch).
You will need to enter 2 things 
- The IP address of the machine.
- The credentials (username/passowrd) to access the device.

The script will sync using telnet to the switch & the Database, then you will get into a Menu, from where you will be able to update (Add/Delete/Rename) Vlans, Or to View the current Database.

It take care of most the wrong input values, like: device reachability, invalid username/password and the value type entered in the Menu.

Syching between the database and the machine is working in the background every 60 sec.

Enjoy!\n"""

################## Device reachability Func #####

#Checking for IP reachability, and if no success, it exists the script.
def ping_check():
	
	switch_ip = raw_input("Please enter the IP address for the Cisco device: ")
	ip_icmp_check = False
	
	while True:

		ping_reply = subprocess.call(['ping', '-c', '3', '-w', '3', '-q', '-n', switch_ip], stdout = subprocess.PIPE)

        	if ping_reply == 0:
                	print "The ping to the following device is reachable %s." %switch_ip
			ip_icmp_check = True
			break

        	elif ping_reply == 2:
      			print Fore.RED + Style.BRIGHT + "\n* No response from device %s." %switch_ip + Fore.WHITE
			ip_icmp_check = False
        	else:
                	print Fore.RED + Style.BRIGHT + "\n* Ping to the following device has FAILED:", switch_ip + Fore.WHITE
			ip_icmp_check = False

		#Asking the user to re-enter the IP, if not valid.
		switch_ip = raw_input("Please re-enter a correct/reachable IP for the device: ")

	return switch_ip

################## Telnet Func ##################

#Telnet to the Switch, either to just fetch the data, or config, depending on a check mark "check_apply_cmds"

def telnet(ip):	
	global username
	global password

	#Define telnet parameters
	TELNET_PORT = 23
	TELNET_TIMEOUT = 5
	READ_TIMEOUT = 5
      
	#Logging to the device
	connection = telnetlib.Telnet(ip,TELNET_PORT, TELNET_TIMEOUT)
	
	cred_output = connection.read_until("name:", READ_TIMEOUT)
	connection.write(username + "\n")
	cred_output = connection.read_until("password:", READ_TIMEOUT)
	connection.write(password + "\n")
	time.sleep(1)
	
	global cred_switch_check
	
	#Checking for credentials provided -- only first time with cred_switch_check
	if cred_switch_check == True:
		time.sleep(2)
		cred_output= connection.read_until("#", READ_TIMEOUT)
		invalid_cred_list = cred_output.split("\n")
		while "Username: " in invalid_cred_list:
			print "INVALID credentials detected, please enter the correct username/password\n"
			connection.close()
			invalid_cred_list = []
					
			#Asking the user to enter the correct credentials
			connection = telnetlib.Telnet(ip,TELNET_PORT, TELNET_TIMEOUT)
			
			username = raw_input("Username: ")
			password = getpass.getpass('Password:')
			
			cred_output = connection.read_until("name:", READ_TIMEOUT)
			connection.write(username + "\n")
			cred_output = connection.read_until("password:", READ_TIMEOUT)
			connection.write(password + "\n")
			time.sleep(3)
					
			cred_output= connection.read_until("#", READ_TIMEOUT)
			invalid_cred_list = cred_output.split("\n")
		
		print "Credentials is accepted"
	
	#Checking if config is needed
	if check_apply_cmds == True:
		#Entering config mode
		connection.write("conf t\n")
		time.sleep(1)
		
		#Addition for Vlan/s names and Descriptions
		for element in range(len(vlanName_add_list)):
			connection.write("vlan " + vlanName_add_list[element] + "\n")
			connection.write("name " + vlanDescr_add_list[element] + "\n")	
			
		#Deletion for Vlan/s.
		for element in range(len(vlanDel_list)):
			connection.write("no vlan " + vlanDel_list[element] + "\n")
		
		#Renaming for Vlan/s.
		for element in range(len(vlanRename_name_list)):
			connection.write("vlan " + vlanRename_name_list[element] + "\n")
			connection.write("name " + vlanRename_descr_list[element] + "\n")
			
		print "Updating the required configuration to the device, please wait..."
		#Saving config
		connection.write("end\n")
		connection.write("write\n")
		#print connection.read_very_eager()	
		time.sleep(15)
	
	#setting terminal length for entire output - no propagation
	connection.write("terminal length 0\n")
	time.sleep(1)
	
	#Entering show mode
	connection.write("show vlan\n")
	time.sleep(1)
		
	#Test for reading command output
	vlan_show = connection.read_very_eager()
	
	#Fetching the vlan names and description and exporting them to lists
	name_list =[]
	descr_list =[]
	for each_line in vlan_show.split("\n"):   				#Iterating on output show
		#print each_line
		if re.search(r"(.+?) +(\w+) +(active) .+", each_line) != None:  #Checking of the right pattern to fetch the name/descr.
			vlan_data = re.search(r"(.+?) +(\w+) +(active) .+", each_line)
			name_list.append(vlan_data.group(1))
			descr_list.append(vlan_data.group(2))
			
			if re.match('1002 fddi-default', each_line) !=None:     #break the loop/process once reaches vlan 1002!
				break
	
	return name_list, descr_list
	#Closing the connection
	connection.close()


################## DB Func ################

#Displaying results on the Database
name_db_list= []
show_DB_vlan_check = False

def db_value_query():
	global name_db_list
	global show_DB_vlan_check
	
	#Displaying results on the Database
	Base = declarative_base()
	
	#Creation for class that matached the Database Table
	
	class vlan_class(Base):
			__tablename__ = 'VLANS'
			Id = Column(Integer, primary_key=True)
			Name = Column(Integer)
			Description = Column(String)
	
	#create_engine() is an instance of Engine, and it represents the core interface for the database
	
	engine = create_engine('sqlite:///sqlite_database')
	
	#Creating the database table using Metadata
	
	Base.metadata.create_all(engine)
	
	#Session creation
	Session = sessionmaker(bind=engine)
	Session.configure(bind=engine)
	session = Session()
	
	#Check if insertion (with True) to the Database is required:
	global insertDB_check
	if insertDB_check == True:
		
		#Verifying if the table is Empty
		if session.query(func.count(vlan_class.Id)).scalar() != 0:
			session.query(vlan_class).filter().delete()
			print "Updating the configuration data to the Database, please wait..."
			time.sleep(5)
		
		#Inserting the values in the table "Id, Name, Description"
		print "The database is being updated!"
		for i in range(len(name_list_output)):
			session.add(vlan_class(Id=i+1, Name=name_list_output[i], Description=descr_list_output[i]))
		name_db_list = name_list_output

	#Only to Query all the values in the Table	
	else:
		id_db_list=[]
		name_db_list=[]
		descr_db_list=[]
		for instance in session.query(vlan_class).order_by(vlan_class.Id):
			if show_DB_vlan_check == True:
				print instance.Id, instance.Name, instance.Description
			id_db_list.append(str(instance.Id))
			name_db_list.append(str(instance.Name))
			descr_db_list.append(str(instance.Description))		

		#print "id_db_list: " + " ".join(name_db_list)	
		#print "name db list: " + " ".join(name_db_list)
		#print "descr db list: " + " ".join(descr_db_list)

		return id_db_list, name_db_list, descr_db_list
		
	session.commit()
	time.sleep(5)

	insertDB_check = False


################## DB Synchronization #######

#Letting db_synch function to check if the Synchronization every 60 sec. can be run or not, depending on both time, and the Menu status! If it's >= 60 sec AND those lists are empty.

synDB_check = False
def db_synch():
	while True:
		time.sleep(60)
		global synDB_check
		global name_list_output
		global name_db_list
		global switch_ip
		global insertDB_check
		global descr_list_output

		if synDB_check == True:
        		sys.stdout.write('\r'+' '*(len(readline.get_line_buffer())+2)+'\r')
        		
			#Compare between the 2 lists to check if we need to write to the database or not
        		#If there is a difference, it takes the date from the switch and apply it on the DB.
			print "\ncomparing between the datadase and switch...\n"
			#print name_db_list
			name_list_output,descr_list_output = telnet(switch_ip)
			#print name_list_output
        		if cmp(name_db_list, name_list_output) != 0:
        			print "There is a discrepancy, and the database needs to be updated, hold on...\n"
         			insertDB_check = True
				show_DB_vlan_check = False
        			db_value_query()
				print "The Database became synched again now!\n"
        			insertDB_check = False
			print "\nAll are okay, the Database is already Synched!\n"
        		sys.stdout.write('Enter your choice: ' + readline.get_line_buffer())
        		sys.stdout.flush()

################## Functions ################

try:

	#Check whether config is needed
	check_apply_cmds = False

	switch_ip = ping_check()

	#Check whether config is needed, and getting the cred_file
	check_apply_cmds = False

	#Check on Username/Password credentials for Switch Access -- Only once th script starts. Later it saved it for future access
	cred_switch_check = True

        #Definning Credentials file
	print "\nPlease enter the required credentials to access the Switch\n"
	username = raw_input("Username: ")
        password = getpass.getpass('Password:')

	name_list_output, descr_list_output = telnet(switch_ip)
	cred_switch_check = False  # To avoid checking for invalid logins, as it was already saved previously

	print "\nSyching between the Database and the Cisco device, Please wait...\n"
	
	#Setting insertDB_check as it's the flag to insert into the database
	insertDB_check = True
	db_value_query()
	
except KeyboardInterrupt:
 	print "\n\nProgram aborted by user. Exiting...\n"
   	sys.exit()

#To catch all Errors
except:
	print "The following Error has just occured: %s" % sys.exc_info()[0]


#Start Threading with timer of 60 sec, to sync the database with the Switch
if __name__ == "__main__":
  	hw_thread = threading.Thread(target = db_synch)
        hw_thread.daemon = True
        hw_thread.start()

################## USER MENU #################
try:	
	#Creating a Time reference
	#Enter option for the first screen to indicate View/Update for Vlans.
	while True:

		#Checkmark to clear the db_synch function to work, if needed
		synDB_check = True

        	print "\nUse this tool to sync/add the Vlans with the machine:\nv - View the updated/synched Vlan Database\nu - Update (Add/Delete/Rename) Vlan/s\n"
        
        	user_option_sim = raw_input("Enter your choice: ")
       		 
        	if user_option_sim == "v":
			synDB_check = False  		#To deny the db_synch for working, and causing any conflicts in the Database
			insertDB_check = False
			show_DB_vlan_check = True	#To show the vlan from the database on the screen
			db_value_query()
			show_DB_vlan_check = False
			time.sleep(1)
			continue
	
		elif user_option_sim == "u":
			
			synDB_check = False  	#To deny the db_synch for working, and causing any conflicts in the Database

                	vlanName_add_list = []
                       	vlanDescr_add_list=[]
			vlanDel_list = []
                      	vlanRename_name_list = []
                       	vlanRename_descr_list=[]
			
			while True:
				
				#2nd Loop to iterate on Update actions and including the synching to the database every about 60 seconds.
				print """\nChoose the designated action/s (Choose all your actions before "Apply"):\nn - New Vlan addition/s\nd - Delete Vlan/s\nr - Rename Vlan/s\na - Apply\ne - Exit to the previous Menu (without Applying anything)"""

				user_option_sim2 = raw_input("Enter your choice: ")

				if user_option_sim2 == "n":
				
					#This section for Vlan addition. We check if more vlans to add at the same time. 
					# Add the new vlan number and name. result in vlan_add_list and vlanName_add_list	
						
					while True:
						check_number_vlans = raw_input("How many vlans you need to add: ")
						if check_number_vlans.isdigit():
							break
						else:
							print "This is not an integer, please re-enter the correct value.."
						
							
					#Iterating on the output for loop counts
                                	for vlan_count in range(int(check_number_vlans)):
						#Add vlan name
						while True:
							#Checking if it's an integer
							while True:
								vlanName_to_update = raw_input("Please enter a/next vlan name to add (i.e.: 100): ")
								if vlanName_to_update.isdigit():
									break
								else:
									print "This is not an integer, please re-enter a vlan name/number.."

							#Checkup for any errors in the vlan number given
                                      			if (vlanName_to_update != "") and (4094 >=  int(vlanName_to_update)) and int(vlanName_to_update) > 1 and int(vlanName_to_update) != 1002|1003|1004|1005:
								break
							else:
								print "Invalid VLAN number, please try again"
								continue
					
						#Add vlan name in a list
						vlanName_add_list.append(vlanName_to_update)
				
						#Add vlan description -- Appending the string input by the user to the list
						vlanDescr_to_update = raw_input("Please enter the vlan description Or press Enter to set the default for Cisco machine: ")

                                        	#If no vlan name, will be set to default.
                                        	if (vlanDescr_to_update == ""):
                                         		vlanDescr_to_update = "VLAN"+ vlanName_to_update
							vlanDescr_add_list.append(vlanDescr_to_update)
						else:	
							vlanDescr_add_list.append(vlanDescr_to_update)
				
				#Deleting Menu part
				elif user_option_sim2 == "d":

					#To delete new Vlan/s. result in vlan_del_list

					#vlan_del_list = []

                                        while True:
                                                check_number_vlans = raw_input("How many vlans you need to delete: ")
                                                if check_number_vlans.isdigit():
                                                        break
                                                else:   
                                                        print "This is not an integer, please re-enter the correct value.."

                                	for vlan_count in range(int(check_number_vlans)):
                                        	#Add vlan name
                                        	while True:
							#Checking if this is an integer
							while True:
                                                		vlanName_to_update = raw_input("Please enter a/next vlan number to delete: ")
								if vlanName_to_update.isdigit():
									break
								else:
									print "This is not an integer, please re-enter the a vlan name/number"

                                                	#Checkup for any errors in the vlan number given
                                                	if (vlanName_to_update != "") and (4094 >=  int(vlanName_to_update)) and int(vlanName_to_update) > 1 and int(vlanName_to_update) != 1002|1003|1004|1005:
                                                        	break
                                                	else:
                                                        	print "Invalid VLAN number"
                                                        	continue

                                		vlanDel_list.append(vlanName_to_update)

				#Renaming -  Menu Part
				elif user_option_sim2 == "r":

					#To rename the current Vlan/s. result in vlan_rename_list.
					#vlanRename_name_list = []
                                	#vlanRename_descr_list=[]

                                        while True:
                                                check_number_vlans = raw_input("How many vlans you need to rename: ")
                                                if check_number_vlans.isdigit():
                                                        break
                                                else:   
                                                        print "This is not an integer, please re-enter the correct value.."

                                	for vlan_count in range(int(check_number_vlans)):
                                        	#Adding vlan name
                                        	while True:
							#Checking if this is an integer
							while True:
                                                		vlanName_to_update = raw_input("Please enter a/next vlan name to renamber: ")
								if vlanName_to_update.isdigit():
									break
								else:
									print "This is not an integer, please re-enter the a vlan name/number"

                                                	#Checkup for any errors in the vlan number given
                                                	if (vlanName_to_update != "") and (4094 >=  int(vlanName_to_update)) and int(vlanName_to_update) > 1 and int(vlanName_to_update) != 1002|1003|1004|1005:
                                                        	break
                                                	else:
                                                        	print "Invalid VLAN number"
                                                        	continue

                                        	#Adding vlan name in a list
                                        	vlanRename_name_list.append(vlanName_to_update)


                                        	#Adding vlan description
                                        	vlanDescr_to_update = raw_input("Please enter a/next vlan name Or press Enter to set the default for cisco machine: ")

                                        	#If no vlan name, will be set to default.
                                        	if (vlanDescr_to_update == ""):
                                                	vlanDescr_to_update = "VLAN"+ vlanName_to_update

                                        	vlanRename_descr_list.append(vlanDescr_to_update)

				elif user_option_sim2 == "a":
					
					#Mark the check mark to apply the config. As the function telnet will check on that.
					check_apply_cmds = True	
					name_list_output, descr_list_output = telnet(switch_ip)
					check_apply_cmds = False	
					
					#Instruct the database to update itself with the new values, check is True for DB insertion
					insertDB_check = True
					db_value_query()
					#To keep the default to fetch and show
					insertDB_check = False
					break

				#Exit to the main Menu - without applying anything
				elif user_option_sim2 == "e":
					break

except KeyboardInterrupt:
    print "\n\nProgram aborted by user. Exiting...\n"
    sys.exit()            

#End of program

