import pandas as pd
import os


def import_files(u_path):
    #Get File names and paths, store in dictionary    
    files = {}
    
    for (root, dirs, file) in os.walk(u_path):
        for f in file: 
            if '.csv' or '.xlsx' in f:
                files[(f[0:9]).replace('-','').replace('_','')] = (f[0:-4] + f[-4:].lower()) #edit filenames, shorten and make it readable, change .CSV to .csv.
                
    return files

def main():
    unsorted_path = r'E:\Documents\Current Finances\Activity\unsorted\Expenses'
    sorted_path = r'E:\Documents\Current Finances\Activity\sorted'
    
    # import files
    filenames = import_files(unsorted_path)
    
    print(filenames)
    
    #Read files and convert to dataframe
        
    # combine files in dataframes by account
    
    #combine accounts by debit/credit

    # export files to excel

if __name__ == '__main__':
    main()