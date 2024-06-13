import pandas as pd
import os

def import_unsortfiles(u_path):
    #Get File names and paths, store in dictionary    
    files = {}
    
    for (root, dirs, file) in os.walk(u_path):
        for f in file: 
            if '.csv' or '.xlsx' in f:
                if f[0:9] not in files.keys(): #if first occurance, create list - if not, append
                    files[(f[0:9]).replace('-','').replace('_','')] = [root + '\\' + (f[0:-4] + f[-4:].lower())]
                else: 
                    files[(f[0:9]).replace('-','').replace('_','')].append(root + '\\' + (f[0:-4] + f[-4:].lower()))
    return files

#global variables
unsorted_path = r'E:\Documents\Current Finances\Activity\unsorted\Expenses'
sorted_path = r'E:\Documents\Current Finances\Activity\sorted'

def main():
    
    # import files
    filenames = import_unsortfiles(unsorted_path)
    
    # print(filenames)
    
    dataframes = {}
    #Read files and convert to dataframe
    for keys, values in filenames.items():
        dataframes [keys] = [pd.read_csv(fn) for fn in values]
        # print(keys, values)
        
    # print(dataframes.items())
    # combine files in dataframes by account
    combined_accounts = {}
    
    for keys, values in dataframes.items():
        combined_df = pd.concat([i for i in values])
        combined_df = combined_df.drop_duplicates()
        combined_accounts[keys] = combined_df
        
    print(combined_accounts.items())
    #combine accounts by debit/credit
    
    # export files to excel

if __name__ == '__main__':
    main()