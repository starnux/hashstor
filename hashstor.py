#!/usr/bin/env python

#--------------------------------------------------------------
# Hash Based compressed based storage
#--------------------------------------------------------------

import os
import sys
import hashlib
import binascii
import datetime
import zlib
import operator
from optparse import OptionParser

BLOCKDIR="%s/blocks"
BLOCKPATH="%s/blocks/%s"
BLOCKPATHZ="%s/blocks/%s.z"
FILEDIR="%s/files"
FILEPATH="%s/files/%s"
STORAGEDIR="%s/storages"
STORAGEPATH="%s/storages/%s"

DEFAULT_STORAGE = "default"
DEFAULT_PATH = ".hashstor"
DIGEST_NAME = "SHA1"
DIGEST_SIZE = 20
CHUNKSIZE=16384

def check_hashstor(path):
    if not os.path.exists(BLOCKDIR % path) or \
       not os.path.isdir(BLOCKDIR % path) or \
       not os.path.exists(FILEDIR % path) or \
       not os.path.isdir(FILEDIR % path) or \
       not os.path.exists(STORAGEDIR % path) or \
       not os.path.isdir(STORAGEDIR % path):
            raise AssertionError, "Invalid or Broken storage point"

def mk_hashstor(path):
    if not os.path.exists(path):
        os.mkdir(path, 0700)
    os.mkdir(BLOCKDIR % path)
    os.mkdir(FILEDIR % path)
    os.mkdir(STORAGEDIR % path)
    fd = open(STORAGEPATH % (path, DEFAULT_STORAGE), "w")
    fd.write("")
    fd.close()

# Completely non optimized way to get all files from a path...
def walk_over_dir(directory):
    f = []
    for root, dirs, files in os.walk(directory):
        baseroot = root.replace(directory, "")
        if baseroot.startswith("."):
            continue
        if len(baseroot) > 0:
            baseroot = baseroot.lstrip("/") + "/"
        for curfile in files:
            if not curfile.startswith("."):
                f.append("%s%s" % (baseroot, curfile))
    return f

def hashstor_delete(hashstor, storage, sha):
    # Check if other storages uses this file before removing
    unused = True

    storage_list = os.listdir(STORAGEDIR % hashstor)
    for s in storage_list:
        if s == storage:
            continue
        storage_data = hashstor_load_storage(hashstor, s)
        if sha in storage_data.keys():
            unused = False

    if unused:
        if not os.path.isfile(FILEPATH % (hashstor, sha)):
            print >> sys.stderr, "Warning : Missing file %s ..." % sha
            return

        files_list = os.listdir(FILEDIR % hashstor)
        blocks = []
        for f in files_list:
            if f == sha:
                continue
            fd_file = open(FILEPATH % (hashstor, f))
            for l in fd_file:
                l = l.rstrip()
                blocks.append(l)

        file_blocks = []
        fd_file = open(FILEPATH % (hashstor, sha))
        for block in fd_file:
            block = block.rstrip()

            # Checking if block is really unused...
            if block in blocks:
                continue

            if os.path.exists(BLOCKPATH % (hashstor, block)):
                os.unlink(BLOCKPATH % (hashstor, block))
                file_blocks.append(block)
            elif os.path.exists(BLOCKPATHZ % (hashstor, block)):
                os.unlink(BLOCKPATHZ % (hashstor, block))
                file_blocks.append(block)
            elif block not in file_blocks:
                print >> sys.stderr, "Warning : Missing block %s ..." % block

        fd_file.close()
        os.unlink(FILEPATH % (hashstor, sha))

def hashstor_extract(hashstor, sha, dest, filename):

    fd_file = open(FILEPATH % (hashstor, sha))

    filedir = os.path.dirname(filename)

    if not os.path.exists("%s/%s" % (dest, filedir)):
        os.makedirs("%s/%s" % (dest, filedir))

    outfile = open("%s/%s" % (dest, filename), "w+")
    md = hashlib.new(DIGEST_NAME)

    for block in fd_file:
        block = block.rstrip()

        if os.path.exists(BLOCKPATH % (hashstor, block)):
            fd_chunk = open(BLOCKPATH % (hashstor, block))
            chunk = fd_chunk.read()
            fd_chunk.close()
        elif os.path.exists(BLOCKPATHZ % (hashstor, block)):
            fd_chunk = open(BLOCKPATHZ % (hashstor, block))
            chunk = zlib.decompress(fd_chunk.read())
            fd_chunk.close()
        else:
            raise AssertionError, "Missing block %s for '%s'" % (block, filename)

        md.update(chunk)
        outfile.write(chunk)

    outfile.close()

    digest = md.digest()
    while len(digest) < DIGEST_SIZE:
        digest = "0%s" % digest
    digest = binascii.hexlify(digest)

    if digest <> sha:
        raise AssertionError, "Invalid extracted file digest %s <> %s for '%s'" % (digest, sha, filename)

def hashstor_load_storage(hashstor, storage):
    storage_data = dict()

    if not os.path.isfile(STORAGEPATH % (hashstor, storage)):
        print >> sys.stderr, "Storage name '%s' does not exist, creating it" % storage
        storage_fd = open(STORAGEPATH % (hashstor, storage), "w+")
        print >> storage_fd, ""
        storage_fd.close()

        return storage_data
    else:
        storage_fd = open(STORAGEPATH % (hashstor, storage), "r")
    
    for line in storage_fd:
        file_data = dict()
        d = line.rstrip().split(" ")
        if len(d) < 3:
            continue
        file_data["size"] = int(d[0])
        file_data["name"] = d[2]
        if d[1] in storage_data.keys():
            storage_data[d[1]].append(file_data)
        else:
            storage_data[d[1]] = [file_data]
    
    storage_fd.close()

    return storage_data

def hashstor_write_storage(hashstor, storage, storage_data):
    
    storage_fd = open(STORAGEPATH % (hashstor, storage), "wb")

    for h in storage_data.keys():
        for f in storage_data[h]:
            print >> storage_fd, "%d %s %s" % (f["size"], h, f["name"])

    storage_fd.close()

def hashstor_store_files(hashstor, storage, basepath, files):
    
    storage_data = hashstor_load_storage(hashstor, storage)

    chunks = 0
    sizegain = 0
    duplicates = 0
    for f in files:
        filepath = "%s/%s" % (basepath, f)
        stat = os.stat(filepath)
        print "Processing '%s' ..." % f
        fd = open(filepath, "rb")
        globalmd = hashlib.new(DIGEST_NAME)
        file_hashes = []
        while True:
            md = hashlib.new(DIGEST_NAME)
            chunk = fd.read(CHUNKSIZE)
            globalmd.update(chunk)
            md.update(chunk)
            sha1 = md.digest()
            while len(sha1) < DIGEST_SIZE:
                sha1 = "0%s" % sha1
            sha1 = binascii.hexlify(sha1)
            file_hashes.append(sha1)
            chunks += 1
            if not os.path.exists(BLOCKPATH % (hashstor, sha1)) and \
               not os.path.exists(BLOCKPATHZ % (hashstor, sha1)):
                c_chunk = zlib.compress(chunk)
                if len(c_chunk) < len(chunk):
                    fd_chunk = open(BLOCKPATHZ % (hashstor, sha1), "wb")
                    fd_chunk.write(c_chunk)
                    sizegain += len(chunk)-len(c_chunk)
                else:
                    fd_chunk = open(BLOCKPATH % (hashstor, sha1), "wb")
                    fd_chunk.write(chunk)
                fd_chunk.close()
            else:
                duplicates += 1
            if len(chunk) < CHUNKSIZE:
                break
        globalsha1 = globalmd.digest()
        while len(globalsha1) < DIGEST_SIZE:
            globalsha1 = "0%s" % globalsha1 
        globalsha1 = binascii.hexlify(globalsha1)
        if not os.path.exists(FILEPATH % (hashstor, globalsha1)):
            fd_file = open(FILEPATH % (hashstor, globalsha1), "wb")
            for i in range(0, len(file_hashes)):
                print >> fd_file, "%s" % file_hashes[i]
            fd_file.close()
        file_data = dict()
        file_data["size"] = stat.st_size
        file_data["name"] = f
        if globalsha1 in storage_data.keys():
            duplicate = False
            for g in storage_data[globalsha1]:
                if f in g["name"]:
                    duplicate = True
            if not duplicate :
                storage_data[globalsha1].append(file_data)
        else:
            storage_data[globalsha1] = [file_data]

    hashstor_write_storage(hashstor, storage, storage_data)

    print "Space saved %d/%s chunks and %d bytes" % (duplicates, chunks, sizegain)

def hashstor_compare_files(hashstor, storage, basepath, files):
    
    storage_data = hashstor_load_storage(hashstor, storage)

    changes = False

    for f in files:
        differs = False
        filepath = "%s/%s" % (basepath, f)
        stat = os.stat(filepath)
        print "Checking '%s' ..." % f
        fd = open(filepath, "rb")
        globalmd = hashlib.new(DIGEST_NAME)
        file_hashes = []
        while True:
            md = hashlib.new(DIGEST_NAME)
            chunk = fd.read(CHUNKSIZE)
            globalmd.update(chunk)
            md.update(chunk)
            sha1 = md.digest()
            while len(sha1) < DIGEST_SIZE:
                sha1 = "0%s" % sha1
            sha1 = binascii.hexlify(sha1)
            file_hashes.append(sha1)
            if not os.path.exists(BLOCKPATH % (hashstor, sha1)) and \
               not os.path.exists(BLOCKPATHZ % (hashstor, sha1)):
                differs = True
            if len(chunk) < CHUNKSIZE:
                break
        globalsha1 = globalmd.digest()
        while len(globalsha1) < DIGEST_SIZE:
            globalsha1 = "0%s" % globalsha1 
        globalsha1 = binascii.hexlify(globalsha1)
        if not os.path.exists(FILEPATH % (hashstor, globalsha1)):
            differs = True
        if differs:
            print "File '%s' is different !" % f
            changes = True

    return changes

if __name__ == '__main__':
    try:
        usage = 'Usage: %prog [options] <command> [command options]\n'\
                '  Parse file and create a HashStor storage point, commands are :\n'\
                '   - init [files or directories] : Initialize storage point, default with all at current directory\n'\
                '   - storages <command> : Manipulate storage names\n'\
                '       - storages list : List all storage names\n'\
                '       - storages delete <storage name> : Delete storage names\n'\
                '   - update [files or directories] : Update with files, default with all at current directory\n'\
                '   - compare [files or directories] : Compare with files, default with all at current directory\n'\
                '   - list [internal path] : List files in the storage point\n'\
                '   - extract <destination directory> [internal file name] : Extract file, default all files\n'\
                '   - delete [internal file name] : Delete file, default entire storage name\n'\
                '   - check : Check integrity\n'
        optparser = OptionParser(usage=usage)
        optparser.add_option('-d', '--hashstor', dest='hashstor',
                             help='HashStor storage point, default .hashstor in current directory')
        optparser.add_option('-c', '--directory', dest='directory',
                             help='Use this directory for base path on file update')
        optparser.add_option('-s', '--storage', dest='storage',
                             help='HashStor storage name, default name is \'%s\'' % DEFAULT_STORAGE)
        optparser.add_option('-v', '--debug', dest='debug',
                             action='store_true',
                             help='Show debug information')
        (options, args) = optparser.parse_args(sys.argv[1:])

        if not options.directory:
            directory = os.getcwd()
        else:
            directory = options.directory.rstrip("/")

        if not options.hashstor:
            hashstor = "%s/%s" % (directory, DEFAULT_PATH)
        else:
            hashstor = options.hashstor.rstrip("/")

        if not options.storage:
            storage = DEFAULT_STORAGE
        else:
            storage = options.storage

        if options.debug:
            print >> sys.stderr, " - HashStor in '%s'\n - Storage name '%s'\n - Directory '%s'" % (hashstor, storage, directory)
        
        if len(args) < 1:
            raise AssertionError, "Please specify command"

        if args[0] == "init":
            if os.path.exists(hashstor):
                raise AssertionError, "Storage already exists"
            mk_hashstor(hashstor)

            if len(args) >= 2:
                sourcedir = args[1].rstrip("/")
            else:
                sourcedir = directory

            # Parse source directory
            files = walk_over_dir(sourcedir)

            hashstor_store_files(hashstor, storage, sourcedir, files)

            sys.exit(0)

        elif args[0] == "update":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            if len(args) < 2:
                paths = ["/"]
            else:
                paths = args[1:]

            for path in paths:
                if not os.path.isdir(path):
                    files = [path]
                    sourcedir = directory
                    hashstor_store_files(hashstor, storage, sourcedir, files)
                else:
                    sourcedir = "%s/%s" % (directory, path.rstrip("/"))

                    # Parse source directory
                    files = walk_over_dir(sourcedir)

                    hashstor_store_files(hashstor, storage, sourcedir, files)

            sys.exit(0)

        elif args[0] == "compare":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            if len(args) < 2:
                paths = ["/"]
            else:
                paths = args[1:]

            for path in paths:
                if not os.path.isdir(path):
                    files = [path]
                    sourcedir = directory
                    if hashstor_compare_files(hashstor, storage, sourcedir, files):
                        sys.exit(1)
                else:
                    sourcedir = "%s/%s" % (directory, path.rstrip("/"))

                    # Parse source directory
                    files = walk_over_dir(sourcedir)

                    if hashstor_compare_files(hashstor, storage, sourcedir, files):
                        sys.exit(1)

            sys.exit(0)

        elif args[0] == "list":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            storage_data = hashstor_load_storage(hashstor, storage)

            if len(args) >= 2:
                internal_path = args[1]
            else:
                internal_path = ""

            for h in storage_data.keys():
                for f in storage_data[h]:
                    if f["name"].startswith(internal_path):
                        print "%d\t%s" % (f["size"], f["name"])

            sys.exit(0)

        elif args[0] == "storages":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            if len(args) < 2:
                raise AssertionError, "Please specify storages command"

            if args[1] == "list":
                storages = dict()
                storage_list = os.listdir(STORAGEDIR % hashstor)
                for s in storage_list:
                    stat = os.stat(STORAGEPATH % (hashstor, s))
                    mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                    storages[s] = { "mtime" : mtime}
                
                storage_list = sorted(storages.iteritems(), key=operator.itemgetter(1))
                for s in storage_list:
                    print " - '%s' (Last Modified on %s)" % (s[0], s[1]["mtime"])

            elif args[1] == "delete":
                
                if len(args) < 3:
                    raise AssertionError, "Please specify storage name to delete"
                
                storage = args[2]

                storage_data = hashstor_load_storage(hashstor, storage)

                for h in storage_data.keys():
                    hashstor_delete(hashstor, storage, h)

                os.unlink(STORAGEPATH % (hashstor, storage))

            else:
                raise AssertionError, "Unknown storages command"

            sys.exit(0)

        elif args[0] == "extract":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            if len(args) < 1:
                raise AssertionError, "Please specify destination directory"

            dest = args[1].rstrip("/")

            storage_data = hashstor_load_storage(hashstor, storage)

            if len(args) >= 3:
                filename = args[2]
            else:
                filename = None
            
            for h in storage_data.keys():
                for f in storage_data[h]:
                    if (filename and f["name"] == filename) or not filename:
                        hashstor_extract(hashstor, h, dest, f["name"])

            sys.exit(0)

        elif args[0] == "delete":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            if len(args) >= 2:
                filename = args[1]
            else:
                filename = None

            storage_data = hashstor_load_storage(hashstor, storage)

            for h in storage_data.keys():
                newlist = []
                for f in storage_data[h]:
                    if (filename and f["name"] == filename) or not filename:
                        print "Removing '%s' ..." % f["name"]
                    else:
                        newlist.append(f)
                if filename and len(newlist) > 0:
                    storage_data[h] = newlist
                else:
                    hashstor_delete(hashstor, storage, h)

            if not filename:
                os.unlink(STORAGEPATH % (hashstor, storage))
            else:
                hashstor_write_storage(hashstor, storage, storage_data)
            
        elif args[0] == "check":

            if not os.path.exists(hashstor) or not os.path.isdir(hashstor):
                raise AssertionError, "Invalid HashStor storage point"

            check_hashstor(hashstor)

            errors = 0

            incomplete_files = []
            orphaned_blocks = []

            print "Listing blocks..."
            # Load all blocks
            blocks_list = os.listdir(BLOCKDIR % hashstor)
            blocks = dict()
            for b in blocks_list:
                if b.endswith(".z"):
                    b = b.rstrip(".z")
                blocks[b] = 0
                
            print "Listing files..."
            # Load all files
            files_list = os.listdir(FILEDIR % hashstor)
            files = dict()
            for f in files_list:
                fd_file = open(FILEPATH % (hashstor, f))
                files[f] = 0
                for l in fd_file:
                    l = l.rstrip()
                    if l in blocks.keys():
                        blocks[l] += 1
                    else:
                        incomplete_files.append(f)
                        print "File %s has missing block %s" % (f, l)
                        errors += 1

            print "Checking blocks association..."
            # Check all blocks
            for b in blocks.keys():
                if blocks[b] < 1:
                    print "Unused block %s" % b
                    orphaned_blocks.append(b)
                    errors += 1

            print "Checking damaged files..."
            # Print damaged files
            storage_list = os.listdir(STORAGEDIR % hashstor)
            for s in storage_list:
                storage_data = hashstor_load_storage(hashstor, s)
                for f in incomplete_files:
                    if f in storage_data.keys():
                        for badfile in storage_data[f]:
                            print "Damaged file '%s' in storage '%s'..." % (badfile["name"], s)
                            errors += 1
                for f in storage_data.keys():
                    if f in files.keys():
                        files[f] += 1

            for f in files.keys():
                if files[f] < 1:
                    print "Orphaned file '%s' ..." % f 

            if errors < 1:
                print "Check finished, storage is clean"
            else:
                print "Storage has errors"
        else:
            raise AssertionError, "Invalid command %s" % args[0]


    except AssertionError, e:
        print >> sys.stderr, "Error: %s" % e
        exit(1)

