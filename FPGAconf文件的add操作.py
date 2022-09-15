import re,os


o_dir = 'D:\MyRespostiry\HLS\PHC_v30\solution1\impl\\vhdl'
os.chdir(o_dir)
print("Current Dir: " + os.getcwd())

filelist = os.listdir(o_dir)
for file in filelist:
    print( "this_block.addFile('./vhdl/{name}');".format(name=file))
