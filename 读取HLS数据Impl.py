import re, os

o_dir = 'D:\MyRespostiry\HLS\PHC_v27\solution_11_nbn\impl\\vhdl'
os.chdir(o_dir)
print("Current Dir: " + os.getcwd())

filelist = os.listdir(o_dir)
for file in filelist:
    print("this_block.addFile('./vhdl/{name}');".format(name=file))


def getdata(input_file):
