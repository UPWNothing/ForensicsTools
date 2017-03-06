#! /usr/bin/python

import sys
import argparse
import os
import subprocess
import hashlib
import re
import logging

try:
    from sqlalchemy import Column, Integer, Float, String, Text
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    import pyPdf
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError as e:
    print "Module `{0}` not installed".format(e.message[16:])
    sys.exit()

Base = declarative_base()


class FileInfo(Base):

    __tablename__ = 'files'

    id = Column(Integer,primary_key=True)
    Filename = Column(String)
    Md5 = Column(String)
    Location = Column(String)
    Type = Column(String)
    Metadata = Column(String)
    Deleted = Column(String)

    def __init__(self,Filename,Md5,Location,Type,Metadata,Deleted):
        self.Filename = Filename.decode("utf-8",'replace')
        self.Md5 = Md5
        self.Location = Location
        self.Type = Type
        self.Metadata = str(Metadata)
        self.Deleted = Deleted

# ============ FileCarving Class ==================
class FileCarving(object):
    def __init__(self, img = ''):
        if img == '' or not os.path.isfile(img):
            raise Exception('Invalid File')

        self.img = img
        self.disk_type = subprocess.check_output(['fsstat','-t',img])
        self.info = subprocess.check_output(['fsstat',img])
        # Default output extracted files to extract folder in current working directory
        self.output_path = os.path.join(os.getcwd(),'extract',img)
        
        self.db = img + '.db'
        self.engine = create_engine('sqlite:///'+self.db, echo=False)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    # Get file entries using fls command
    # return ([{undeleted_file_loc,undeleted_file_name},..],[{deleted_file_loc,deleted_file_name}])
    def get_file_entries(self):
        # use fls command to list all the files in disk image
        try:
            undeleted = subprocess.check_output(['fls','-F','-p','-r','-u',self.img])
            deleted = subprocess.check_output(['fls','-F','-p','-r','-d',self.img])
        except Exception as e:
            print e
        
        self.undeleted_entries = parse_file_list(undeleted)
        self.deleted_entries = parse_file_list(deleted)
        return (self.undeleted_entries,self.deleted_entries)
    

    def file_carving(self):
        try:
            subprocess.check_output(["tsk_recover","-e",self.img,self.output_path])
            #subprocess.check_output(["tsk_loaddb","-h",self.img])
        except Exception as e:
            print e


    # extract files to given dest
    def get_file_info(self,file_ents):
        #check if output_dir existed. 
        if not os.path.isdir(self.output_path):
            self.file_carving()
        info = []
        for ent in file_ents:
            loc = ent['loc']
            fname = ent['file_name']
            ftype, meta = get_meta(os.path.join(self.output_path,fname))
            md5 = "-"
            if ftype != "other":
                md5 = get_md5(os.path.join(self.output_path,fname))
            info.append({"Location":loc,"Filename":fname,"Md5":md5,"Type":ftype,"Metadata":meta})
        return info

    def generate_db(self,undeleted_info,deleted_info):
        #if not self.undeleted_info:
        #    self.undeleted_info = self.get_file_info(self.undeleted_entries)
        #if not self.deleted_info:
        #    self.deleted_info = self.get_file_info(self.deleted_entries)

        for entry in undeleted_info:
            new_entry = FileInfo(Deleted="undeleted",**entry)
            self.session.add(new_entry)
            self.session.commit()
        for entry in deleted_info:
            new_entry = FileInfo(Deleted="deleted",**entry)
            self.session.add(new_entry)
            self.session.commit()

    def generate_report(self,undeleted_info,deleted_info):
        #if not self.undeleted_info:
        #    self.undeleted_info = self.get_file_info(self.undeleted_entries)
        #if not self.deleted_info:
        #    self.deleted_info = self.get_file_info(self.deleted_entries)
        
        with open("report_{0}.txt".format(self.img),"w") as f:
            f.write('Files Information in {0}:\n\n'.format(self.img))
            f.write('='*60+'\n')
            f.write('Undeleted Files\n')
            f.write('='*60+'\n\n')
            
            for entry in undeleted_info:
                f.write('Filename:\t\t{0}\n'.format(entry['Filename']))
                f.write('Type:    \t\t{0}\n'.format(entry['Type']))
                f.write('Location:\t\t{0}\n'.format(entry['Location']))
                f.write('Md5:     \t\t{0}\n'.format(entry['Md5']))
                f.write('Metadata:\t\t{0}\n\n'.format(entry['Metadata']))
            
            f.write('='*60+'\n')
            f.write('Deleted Files\n')
            f.write('='*60+'\n\n')
            
            for entry in deleted_info:
                f.write('Filename:\t\t{0}\n'.format(entry['Filename']))
                f.write('Type:\t\t{0}\n'.format(entry['Type']))
                f.write('Location:\t\t{0}\n'.format(entry['Location']))
                f.write('Md5:\t\t{0}\n'.format(entry['Md5']))
                f.write('Metadata:\t\t{0}\n\n'.format(entry['Metadata']))

# =================== End FileCarving Class ================================





# Parse the output of "fls -F -p -r img"
def parse_file_list(file_list):
    entries = []
    for line in file_list.split('\n'):
        if not line:
            continue
        try:
            loc = line.split(' ',1)[1].split('\t')[0][:-1]
            file_name = line.split(' ',1)[1].split('\t')[1]
        except Exception:
            print 'Error: Cannot split the given string: ' + line
        entries.append({"loc":loc,"file_name":file_name})
    return entries

# calculate md5
def get_md5(fname):
    with open(fname) as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5
            
def get_meta(fname):
    ftype = subprocess.check_output(['file','-b',fname])
    info = []
    if "PDF" in ftype:
        ftype = 'pdf'
        try:
            pdf = pyPdf.PdfFileReader(file(fname, 'rb'))
            info = pdf.getDocumentInfo()
        except:
            info = ['Cannot get Metadata']
    elif ftype[0:3] in ['JPE','PNG','GIF','TIF']:
        ftype = 'image'
        with Image.open(fname) as f:
            try:
                exif_data = f._getexif()
                if exif_data:
                    for (k,v) in exif_data.items():
                        info.append('%s:%s'%(TAGS.get(k),v))
            except:
                info = ['Cannot get Exif Data']
    else:
        ftype = 'other'
    return (ftype,info)
    


def main(argv):
    parser = argparse.ArgumentParser(description='Extract files from disk images')
    parser.add_argument('img', nargs='+', help='Disk Image(s) to be analyzed;')
    args = parser.parse_args()

    for test in args.img:
        #try:
        if os.path.isfile(test):
            fc = FileCarving(test)
            fc.file_carving()
            undeleted,deleted = fc.get_file_entries()
            deleted_info = fc.get_file_info(deleted)
            undeleted_info = fc.get_file_info(undeleted)
            fc.generate_db(undeleted_info,deleted_info)
            fc.generate_report(undeleted_info,deleted_info)
        else:
            print 'Not File' 
        #except Exception as inst:
        #    print inst

if __name__ == '__main__':
    main(sys.argv)
