import re,os

o_dir = 'D:\MyRespostiry\MatlabData\Data20220818'
os.chdir(o_dir)
print("Current Dir: " + os.getcwd())

filelist = os.listdir(o_dir)
for file in filelist:
    print("-----")
    print("old filename : " + file)
    oldstring = repr("1807722_Inv")
    newstring = "N1_20220819"
    newfilename = re.sub(oldstring, newstring, file)
    os.rename(file,newfilename)
    print("new filename : " + newfilename)
    print("-----")

print(newfilename)