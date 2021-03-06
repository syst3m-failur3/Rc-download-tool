#! /usr/bin/python 3
"""
Scrapes http://www.readcomics.net and creates .cbz files from
downloaded image files.

The sites Robots.txt file
User-agent: *
Disallow: 
Disallow: /cgi-bin/

Creates instance of GetComic class(the only class in the module :P),
and calls the setup method which gets the home directory where all files will
be stored and invokes the home method, which is the main text menu of the script
where all other functions are called from.

*************************
#  Some Things To Note  #
*************************
1)The sites html is pretty simple to scrape, however there were some issues with
consistency, found that some of the chapter listings were out of order or numbered wrong completely.
Ive attempted to remedy this a bit.

2)Some sleep periods have been placed between the downloading of images
as to be nice to their servers.They mey need to be adjusted.

3)Some chapters are just non existant(ugh) when the error is raised it simply notifys the user and 
continues(they really need to clean up the site a bit :P)


*************************
#      To Do list       #
*************************
1)General code cleanup and random attempts at optimizing whats already here.
2)Fix the freaking search function its no bueno and does not worko
3)Write better Doc strings

"""
from bs4 import BeautifulSoup as bs
import calendar
import datetime
from distutils.dir_util import copy_tree as dis_copy
from getpass import getpass as maskinput
import glob
import json
import os
import requests as re
import re as regx
import shutil
import sys
from tempfile import TemporaryFile
import textwrap
import time
import tkinter as tk
from tkinter import filedialog
from tqdm import tqdm
import webbrowser
import zipfile

class GetComic():
    def __init__(self):
        """Scrapes readcomics.net and Creates '.cbz' files from 
           downloaded images"""
        self.last_dir = None
        self.last_chapter_name = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.home_dir = self.setup()
        self.comicList = 'http://www.readcomics.io/comic-list'
        self.pull_load = False
        self.leave = False
        self.clean_up = True        
        self.pull_list = {}
        self.book_lib = {}
        self.todays_date = datetime.date.today()
        self.day = calendar.day_name[self.todays_date.weekday()]

    def setup(self):
        """
        Gets directory path where the cbz files are to be saved and 
        serializes it as a json file.If the file already exists,
        loads its contents into home_dir attribute 
           
        Returns
        -------
        output(string):
            path to directory
        """
        if 'config.json' in os.listdir(os.path.dirname(os.path.abspath(__file__))):
            with open('config.json',) as infile:
                data = json.load(infile)
                self.last_dir = data['last'][0]
                self.last_chapter_name = data['last'][1]
            return data['home']
        else:
            print("Home Configuration file ('config.json') not Found.\n")
            time.sleep(1)
            print('Please Select A home Directory where all Files will Be saved.')
            time.sleep(2)
            while True:
                root = tk.Tk()
                root.withdraw()
                path = filedialog.askdirectory()
                try:
                    if path == '':
                        pass
                    elif os.path.exists(path):
                        self.home_dir = path
                        print('\nHome Directory:',path,'saved.')
                        time.sleep(2)
                        self.update_config()
                        print("\033c")
                        return path
                except PermissionError:
                    print('Access Denied! Application does not have permission\
                          to access desired location!')
                    os.chdir(self.home_dir)
                    time.sleep(3)
                    print("\033c")
                    break
                except FileNotFoundError:
                    print('No such directory.:',path)
                    os.chdir(self.home_dir)
                    time.sleep(3)
                    print("\033c")
    
    def get_list(self,src):
        """
        Retrieves chapter href links, book title,and the books description.
        
        Sends a request to readcomics.net comic display page
        ex. http://www.readcomics.net/comic/batman Parses code for 
        the above items

        Parameters
        ----------
        src(string): 
            Html link to comic's page 
        
        Returns
        -------
        output(tuple):
            returns a tuple containing the books title, 
            a modified title(that has all illegal filename/directory chars 
            removed,a list of hrefs(the chapters),and the books description
        """
        page = re.get(src)
        page.raise_for_status()
        soup = bs(page.text,"lxml")
        soup_book_name = soup.find('strong').getText()
        corrected_book_name = self.directory_name_check(soup_book_name)
        description = soup.find('p').getText()
        chapters = soup.find_all('a',{'class':'ch-name'},href = True)
        ch_list = [os.path.join(ch['href'],'full') for ch in chapters]
        chap_dates = [i.text for i in soup.find_all('span')][12:-2]
        book_info = soup.body.find('div',attrs= {'class': 'manga-details'})
        book_i_list = [i.text.strip() for i in book_info.find_all('td')]
        return corrected_book_name,ch_list,description,book_i_list,chap_dates

    def convert_chapter_name(self,title,url):
        """
        $Not in use anymore not going to be deleted incase that 
        changes
        
        converts a number string to its english word equivalent
        i.e: '1' ==> 'One'.
        
        Parameters
        ----------
        title(string):
            String representing the book title
        url(string):
            html link to book chapter

        Returns:
        --------
        Output(string):
            a concatnated string representing the title and chapter number.  
        """
        ending = self.get_chap_num(url)
        #print(ending)
        if ending == '00':
            new = num2words(0)

        elif '-' in ending:
            temp = ending.split('-')
            temp[0] = num2words(int(temp[0]))
            temp[-1] = num2words(int(temp[-1]))
            new = ''.join([temp[0],'-',temp[-1]])

        else:
            new = num2words(int(ending))
        return ''.join([title,' ','Chapter',' ',ending])
            
    def directory_name_check(self,dir_name):
        """
        Removes illegal characters from the string
        that the directory will be named with.

        (/, \\, <, |, >, *) All become an empty single space substrings(' ').
        (?,:) become empty substrings with no spacing ('').
        (") double quotes become (')the single quotes
        loops until all illegal characters are removed

        Parameters
        ----------
        dir_name(string): 
            String representing book title that may contain illegal characters.
           
        Returns
        -------
        output(string): 
            a legal directory name
        """
        mapping = [ ('/', ' '), ('\\', ' '), ('"',"'"), (':', ''), ('<', ' '),\

                    ('>', ' '), ('|'," "), ('*', ' '), ('?', ''), ]
        for k, v in mapping:
            dir_name = dir_name.replace(k, v)
        return dir_name
        
    def download_chapter(self,book_dir_title,link):
        """
        Downloads indivdual chapters from selected series.
           
        Creates a directory using the book_dir_title argument and 
        checks to see if a file of the same name exists as to avoid
        making any unnecessary requests.
        if a matching file name is not found,
        method parses code and retrieves all links inside [IMG] tags
        from page's source code

        Displays a simple progress bar from the tqdm library as it
        iterates over the list of links,Entering a second loop
        inside the 'with' context manager and downloads the file bit by bit
        before closing it.
        
        Parameters
        ----------
        book_dir_title(string):
            Name of series   
        link(string):
            html link to books chapter
         
        Returns
        -------
        output:None
        """
        try:
            pages = []
            if not os.path.isdir(os.path.join(self.home_dir,book_dir_title)):
                os.mkdir(book_dir_title)
            ch_name = ''.join((book_dir_title,' ','Chapter',' ',self.get_chap_num(link)))
            if os.path.isfile(os.path.join(self.home_dir,book_dir_title,ch_name+'.cbz')):
                print()
                print('Chapter Already Downloaded.')
                time.sleep(1)
                print()
                print("\033c")
                return
            os.chdir(book_dir_title)
            print(book_dir_title)
            print('Downloading: {}.'.format(ch_name))
            print('Press Ctrl + C to cancel.')
            self.last_dir = os.getcwd()
            self.last_chapter_name = ch_name
            self.update_config()
            chapter_page = re.get(link)
            chapter_page.raise_for_status()
            ch_soup = bs(chapter_page.text,'lxml')
            ch_list = [i['src'] for i in ch_soup.find_all('img')]
            del ch_list[0]
            for index,item in enumerate(tqdm(ch_list),start = 1):
                if index <= 9:
                    name = ''.join([ch_name,' ','0',str(index),'.jpg'])
                else:
                    name = ''.join([ch_name,' ',str(index),'.jpg'])
                pages.append(name)
                res = re.get(item)
                res.raise_for_status()
                with open(name, mode = 'wb') as out:
                    for chunk in res.iter_content(10000):
                        out.write(chunk)
                    time.sleep(.4)
            self.createCbz(ch_name,os.getcwd(),pages)
            os.chdir(self.home_dir)
            print('Done!')
            time.sleep(2)
            print("\033c")
            
        except KeyboardInterrupt:
            print("\033c")
            print('Operation Terminated by User')
            print('\rCleaning Up...')
            path = os.path.join(self.home_dir,book_dir_title)
            if os.getcwd() != path:
                os.chdir(path)
            try:
                if len(pages) != 0:
                    for pics in pages:
                        os.remove(pics)
                os.chdir(self.home_dir)
                os.rmdir(path)
                
            finally:
                print('Returning...')
                #os.chdir(self.home_dir)
                time.sleep(2)
                print("\033c")
                self.leave = True
                return 
            
        except re.exceptions.HTTPError:
            print('There was a problem retrieving files.')
            print('...')
            time.sleep(1)
            print('Cleaning Up.')
            print('Continuing...')
            time.sleep(1.2)
            os.chdir(self.home_dir)
            print("\033c")
            
    def choose_chapter_list(self,name,links,dates):
        """
        Displays a list of issues for a given series
        and allows user to make a selection from the list.
         
        Parameters
        ----------
        name(string):
            Name of book
        links(list):
            list of chapter links for given book
        dates:
        
        Returns
        -------
        output(int):
            interger representing the Issue Number
            used to get link by index from list.
        """
        print("\033c")
        links.sort(key = self.natural_key)
        while True:
            print('####################')
            print('#  Chapter Select  #')
            print('####################\n')
            print("Press: 'q' or type: 'back' to return\n")
            for index,item in enumerate(links,start = 1):
                #subtracts 1 inorder to keep the index correct since we started at one in the line above
                print('{0}){1}{2:>10}'.format(index,name,dates[index-1]))
            choice = input('>>>')
            if choice in ('back','b','q'):
                print("\033c")
                return
            elif choice.isdigit():
                 #Again,subtracts 1 inorder to keep the index correct
                issue_number = int(choice)-1
                if issue_number in range(len(links)):
                    print("\033c")
                    return issue_number
            else:
                print('Invalid Entry')
                time.sleep(1)
                print("\033c")
            
    def natural_key(self,string_):
        """
        See http://www.codinghorror.com/blog/archives/001018.html
        Used Reg Ex to create a key for sorting list in 'Natural' Order
        
        Parameters
        ----------
        string_(string):
            string for sorting
        
        Returns
        -------
        output(list):
            returns key for sorting
        """
        return [int(s) if s.isdigit() else s for s in regx.split(r'(\d+)', string_)]

    def get_chap_num(self,link):
        ''' '''
        if link.endswith('/full'):
            temp = list(link)
            del temp[-5:]
            link = ''.join(temp)
        cut_num = link.rfind('r') + 2
        return link[cut_num:]
        
    def book_display(self,src):
        """
        Basic Text menu, to display information and download options
        for a given series.

        Parameters
        ----------
        src(string):
            url for book to feed get_list function
        
        Returns
        -------
        Output:None
           

        Allows for the download of indivdual as well as multiple chapters
        if the optional argument 'add_option is set to True,
        displays another option 'F' which allows the user to add a series to the
        pull list
        """
        print("\033c")
        title,chapters,description,book_details,chap_dates = self.get_list(src)
        chapters.sort(key = self.natural_key)
        title_length = len(title) + 2
        ch_list_length = len(chapters)
        start_num = chapters[0].rfind('-')+ 1
        latest_num = chapters[-1].rfind('-') + 1
        dir_exists = False
        if  title not in self.pull_list.keys():
            add_option = True
        else:
            add_option = False
        while True:
            print()
            print('='* title_length)
            print(''.join(('#',title,'#')))
            print('=' * title_length)
            print('Issues:',ch_list_length)
            print('First:{} #{}'.format(title,self.get_chap_num(chapters[0])))
            print('Latest:{} #{}'.format(title,self.get_chap_num(chapters[-1])))
            print()
            print('Menu')
            print('A)Description.')
            print('B)Download First Ch.')
            print('C)Download Latest Ch.')
            print('D)Download All.')
            print('E)Choose Chapter.')
            if add_option:
                print('F)Add to Pull List.')
            else: 
                print('F)Remove from Pull List.')
            if os.path.isdir(title):
                dir_exists = True
                print('G)Delete Folder.')
                print('O)Open Folder')
            else:
                dir_exists = False  
            print('Q)Back')

            choice = ''.join(input('>>> ').split()).lower()  
            if choice == 'q':
                print("\033c")
                break
            elif choice == 'a':
                print('\033c')
                print('###############')
                print('# Description #')
                print('###############')
                print('\n'.join(textwrap.wrap(description)).strip())
                print()
                for heading,entry in zip(book_details[::2],book_details[1::2]):
                    print(heading,entry)
                maskinput('\nPress Enter To Continue.')
                print('\033c')

            elif choice == 'b':
                self.download_chapter(title,chapters[0])
   
            elif choice == 'c':
                self.download_chapter(title,chapters[-1])
                
            elif choice == 'd':
                for index,chap in enumerate(chapters,start = 1):
                    if self.leave == True:
                        self.leave = False
                        break    
                    print('Chapter {} of {}'.format(index,len(chapters)))
                    self.download_chapter(title,chap)
                    time.sleep(.6)
                    
            elif choice == 'e':
                issue_number = self.choose_chapter_list(title,chapters,chap_dates)
                if type(issue_number) == int:
                    self.download_chapter(title,chapters[issue_number])

            elif choice == 'f':
                if add_option:
                    self.pull_list[title] = src
                    self.update_pull()
                    add_option = False
                    print(title,'added to Pull List')
                    time.sleep(2)
                    print('\033c')

                elif title in self.pull_list.keys():
                    add_option = True
                    del self.pull_list[title]
                    self.update_pull()
                    print(title,'removed from Pull List')
                    time.sleep(2)
                    print('\033c')
            
            elif choice == 'g' and dir_exists: 
                print('\033c')
                while True:
                    print('################')
                    print('#{0} Warning! {0}  #'.format(u"\u26A0"))
                    print('################')
                    print('Continuing will erase the contents of:')
                    print(os.path.join(self.home_dir,title))
                    decision = ''.join(input('Continue(Y/N)? >>> ').split()).lower()
                    if decision in ('y','yes','ya'):
                        print('Deleting...')
                        tqdm(shutil.rmtree(os.path.join(self.home_dir,title)))
                        print('Folder Deleted')
                        maskinput('Press Enter to Continue.')
                        break
                    elif decision in ('n','nah','no'):
                        break
                    else:
                         print('Ivalid entry!')
                         print('\033c')
                print('\033c')
                    
            elif choice == 'o' and dir_exists: 
                check = os.system('xdg-open "%s"' % title)
                print('\033c')
                if check != 0:
                    print('An error occurred! The containting folder could not be opened!')
                    maskinput('Press Enter to Continue.')
                print('\033c')
            else:
                print()
                print('Invalid Entry!')
                time.sleep(1)
                print('\033c')
                
                
    def createCbz(self,name,src,dst = '.',page_list = []):
        """
        Creates zip archive, writes pages, and changes
        ext to '.cbz'

        changes to a given directory, uses glob to get a list
        of all files with the 'jpg' ext.
        does a sort on the glob list and using the 'with'
        context manager in combination with zipfile,
        it iterates over the list, adding it to the zip then calls
        os.remove() to delete the file from the directory.
        a new name for the zip is made by splitting the file name from the zip
        extension and joining the file name to its new '.cbz' extension
        
        Parmeters:
        ---------
        name(string):
            Name
        """
        os.chdir(src)
        zip_name = ''.join((name,'.zip'))
        if page_list:
            pages = page_list
        else:    
            pages = glob.glob('*jpg')
        pages.sort(key = self.natural_key)
        #Compresses zipfile but little slower to open
        with zipfile.ZipFile(zip_name,mode = 'w',compression = zipfile.ZIP_DEFLATED) as page: 
            for i in pages:
                page.write(i)
                os.remove(i)
        new_name = ''.join((os.path.splitext(zip_name)[0],'.cbz'))
        os.rename(zip_name,new_name)
        
    def load_pull(self):
        """
        Loads in pull_list.config.

        Creates pull list.json file if one does not already exist in 
        the directorythen creates an empty dictionary assining it 
        to the pull_list attribute.
        otherwise opens file and saves pull_list.config contents to 
        the pull_list class attribute
        
        Return
        ------
        output(None):
        """
        file_path = os.path.join(self.script_dir,'pull list.json')  
        if not os.path.isfile(file_path)or os.path.getsize(file_path) == 0 :
            with open(file_path,'w') as out:
                json.dump({},out)
            self.pull_list = {}
            return

        with open(file_path) as infile:
            self.pull_list = json.load(infile)

    def update_pull(self):
        """Creates pull list.json if it doesn't already exist in the directory.
           opens 'pull list.json' and saves it the 'data' variable updates it with the current
           dictionary in the pull_list attribute and opens the json file one final time
           to save the dictionary to file"""     
        file_path = os.path.join(self.script_dir,'pull list.json')  
        if not os.path.isfile(file_path)or os.path.getsize(file_path) == 0 :
            with open(file_path,'w') as out:
                json.dump(self.pull_list,out)
        else:
            with open(file_path) as infile:
                        data = json.load(infile)
            data.update(self.pull_list)

            with open(file_path,'w') as out:
                json.dump(self.pull_list,out)
        
    def update_config(self):
        """
        """
        file_path = os.path.join(self.script_dir,'config.json')  
        config = {'script':self.script_dir,'home':self.home_dir,'last':[self.last_dir,self.last_chapter_name]}
        with open(file_path,'w') as out:
            json.dump(config,out)
            
    def download_pull_list(self):
        """Displays contents dictionary keys from pull list attribute.

           if user input in range of the of the length of the list of
           keys, retireves the corresponding link, and then calls self.book_display
           to show the overview and download options"""
        
        print("\033c")
        self.load_pull()
        if not self.pull_list:
            print()
            print('Pull List empty!')
            print()
            time.sleep(1)
            print("\033c")
            return
        while True:
            book_list = [i for i in self.pull_list.keys()]
            book_list.sort()
            numbered_list = [''.join((str(i),')',book_list[i])) for i in range(len(book_list))]
            print('#############')
            print('# Pull List #')
            print('#############')
            print("Press: 'q' or type: 'back' to return\n")
            for comic in numbered_list:
                print(comic)
            choice = ''.join(input('>>> ').split()).lower()
            if choice in ('back','b','q'):
                print("\033c")
                return
            elif choice.isdigit() and int(choice) in range(len(book_list)):
                book_link = self.pull_list.get(book_list[int(choice)])
                self.book_display(book_link)
            else:
                print('Invalid Entry')
                time.sleep(1)
                print("\033c")

    def edit_pull_list(self):
        """Allows user to add or delete entries to the pull list json file"""
        
        self.load_pull()
        print("\033c")
        while True:
            print('###################')
            print('#  Pull List Edit #')
            print('###################')
            print("Press: 'q' or type: 'back' to return\n")
            print('A) Add to Pull List')
            print('B) Delete Pull List entry')
            print('Q) Back')
            choice = input('>>> ').lower()
            if choice == 'q':
                print("\033c")
                break
            elif choice == 'a':
                print("\033c")
                self.library_search()
            elif choice == 'b':
                if not self.pull_list:
                    print("\033c")
                    print('Pull list empty!')
                    time.sleep(2)
                    print("\033c")
                else:
                    print("\033c")
                    break
        
        while True:
            comic_list = [i for i in self.pull_list.keys()]
            comic_list.sort(key = self.natural_key)
            numbered_list = [''.join((str(i),')',comic_list[i])) for i in range(len(comic_list))]
            if not self.pull_list:
                print('Pull list empty!')
                time.sleep(2)
                print("\033c")
                break             
            print('#####################')
            print('# Pull Entry Delete #')
            print('#####################')
            for i in numbered_list:
                print(i)
            print('\nWhat would you like to delete?')
            del_choice = ''.join(input('>>> ').split()).lower()  
            if del_choice in ('back','b','q'):
                print("\033c")
                break
            elif del_choice.isdigit():
                del_choice = int(del_choice)
                if del_choice in range(len(comic_list)):
                    print('Deleting',comic_list[del_choice])
                    time.sleep(2)
                    del self.pull_list[comic_list[del_choice]]
                    self.update_pull()
                    print("\033c")   
                else: 
                    print('Invalid Entry')
                    time.sleep(1)
                    print("\033c")                
            else:
                print('Invalid Entry')
                time.sleep(1)
                print("\033c")
        
    def overwrite_check(self,files,dst):
        """Verifys if files to be moved, that exist in another directory, are ok to be
           overwritten"""
        
        print("\033c")
        while True:
            print('These files/directories already exist at:',dst,'\nand will cannot be transferred')
            for i in files:
                print(i)
            print('Overwrite(Y/N)?')
            choice = ''.join(input('>>> ').split()).lower()  
            if choice in ('yes','y'):
                return True
            elif choice in ('no','n'):
                return False
            else:
                print('Invalid Entry!')
                time.sleep(1)
                print("\033c")

    def library_load(self):
        """Attempts to establish connection to webpage and gathers all
           hrefs from side source code.

           Uses requets to connect to readcomics.net, then parses
           the html(with Beautiful Soup) and extracts all the href links using
           a list comprhension.
           Finally uses a for loop to iterate over the list and places the comics title(key)
           and corresponding href links(value) into a dictionary"""
        try:
            page = re.get(self.comicList)
            soup= bs(page.text,'lxml')
            bad_links = (r'http://www.readcomics.io/',r'http://www.readcomics.io/advanced-search',\
                         r'http://www.readcomics.io/popular-comic',r'http://www.readcomics.io/comic-list',\
                         r'http://www.readcomics.io/comic-updates')
        
            links = [i['href'] for i in soup.select('ul > li > a') if i['href'] not in bad_links]
            for i in links:
                temp_list = list(i)
                del temp_list[:31] #comic name
                temp_join = ''.join(temp_list)
                title = temp_join.replace('-',' ')
                self.book_lib[title] = i

        except req.HTTPError:
            print("\033c")
            print('Failed to load library.')
            print('Please check your connection and restart Application.')
            print('Terminating')
            sys.exit(1)

    def library_search(self):
        """Simple text menu that waits for user input on their preferred method
           of searching calls keyword_search() with/without optional 'abc'
           argument"""
            
        print("\033c")
        while True:
            print('#############')
            print('#  Library  #')
            print('#############\n')
            print('A)Search by keyword')
            print('B)Search by Letter')
            print('C)Search All')
            print('Q)Back')
            choice = ''.join(input('>>> ').split()).lower()  
            if choice == 'q':
                print("\033c")
                break
            elif choice == 'a':
                self.keyword_search()
            elif choice == 'b':
                self.keyword_search(abc = True)
            elif choice == 'c':
                pass
             
            
            else:
                print('Invalid Entry')
                time.sleep(1)
                print('\033c')

    def keyword_search(self,abc = False):
        """"Takes a user string and searches through the library for a match

            Gets input from user,and then uses a list comprehension
            to loop over all the keys in the self.book_lib attribute and
            adds them to the list if part of the user generated string is
            containted within the key string.

            If no matches are found prints 'No results found!', clears screen
            and enters a new loop where it prompts the user to search again.

            If the 'abc' argument is sent to True:
            allows user to display all comics whose first character matches the users
            entry"""
        
        print("\033c")
        if abc == True:
            word = '  Abc  '
        else:
            word = 'Keyword'
        while True:
            print('#####################')
            print('#  Search({})  #'.format(word))
            print('#####################')
            print("Type: '00' to return \n")
            selection = ''.join(input('>>> ').split()).lower()  
            if selection in ('00'):
                print("\033c")
                return
            if abc == True:
                comics = [i.lower() for i in self.book_lib if i[0] == selection[0]]
            else:
                comics = [i.lower() for i in self.book_lib if selection in i]
                
            if len(comics) == 0:
                print('No Results Found!')
                time.sleep(2)
                print("\033c")
                while True:
                    print('Search Again?')
                    again = input('>>> ').lower()
                    if again in ('y','yes'):
                        break
                    elif again in ('n','no'):
                        return 
            else:
                break
        print("\033c")
        comics.sort(key = self.natural_key)
        numbered_list = [''.join((str(i),')',comics[i])) for i in range(len(comics))]
        while True:
            print('####################')
            print('#  Search Results  #')
            print('####################\n')
            print('Showing Matches for: {}'.format(selection))
            print('{} result(s) found\n'.format(len(comics)))
            for result in numbered_list:
                print(result.title())
            pick = ''.join(input('>>> ').split()).lower()  
            if pick in ('back','b','q'):
                print("\033c")
                return
            elif pick.isdigit():
                if int(pick) in range(len(comics)):
                    book_link = self.book_lib[comics[int(pick)]]
                    self.load_pull()
                    if book_link not in self.pull_list.values():
                        self.book_display(book_link)
                    else:
                        self.book_display(book_link)
            else:
                print('Invalid Entry!')
                time.sleep(1)
                print('\033c')

    def options(self):
        """Displays a list of operations for user to invoke.

           allows user to erase their collection, 
           clear the pull list json file, as well as
           change the home directory."""
           
        print("\033c")
        while True:
            print('#############')
            print('#  Options  #')
            print('#############\n')
            print('A)Delete Pull List')
            print('B)Delete Collection')
            print('C)Change Home Directory')
            print('D)Clean Up Configuration')
            print('Q)Back')
            choice = ''.join(input('>>> ').split()).lower()
            if choice not in ('a','b','c','q'):
                print('Invalid Entry!')
                time.sleep(1)
                print('\033c')
            elif choice == 'q':
                print("\033c")
                break
            elif choice == 'a':
                print("\033c")
                while True:
                    print('Are You sure you want to delete Your Pull List?')
                    print('All information will be lost')
                    del_choice = ''.join(input('Delete pull list?(y/n)>>> ').split()).lower()
                    if del_choice in ('y','yes','ya'):
                        self.pull_list = {}
                        self.update_pull()
                        print('\nPull List Cleared..')
                        time.sleep(2)
                        break
                    elif del_choice in ('n','no','q'):
                        break
                    else:
                        print('Invalid Entry!')
                        time.sleep(1)
                        print("\033c")
                print("\033c")

            elif choice == 'b':
                print("\033c")
                while True:
                    print('Are You sure you want to delete Your collection located at:\n',\
                        os.getcwd())
                    print('All Files in folder will be Deleted.')
                    del_choice2 = ''.join(input('Delete Collection(y/n)>>> ').split()).lower()
                    if del_choice2 == 'y':
                        contents = os.listdir()
                        print('\nDeleting Files')
                        for i in tqdm(contents):
                            if os.path.isdir(i):
                                shutil.rmtree(i)
                            #else: 
                                #os.remove(i) #Deletes files not in folders
                        print('Files Removed')
                        time.sleep(2)
                        break    
                    elif del_choice2 == 'n':
                        break
                    else:
                        print('Invalid Entry!')
                        time.sleep(1)
                        print("\033c")
                print("\033c")
            elif choice == 'c':
                self.change_dir()
    
    def change_dir(self):
        """ """
        print("\033c")
        while True:
            print('Current Directory:',os.getcwd())
            print('Would You like to change directories?')
            dir_choice = ''.join(input('>>> ').split()).lower()
            if dir_choice not in ('n','no','q','quit','yes','y'):
                print('Invalid Entry!')
                time.sleep(1)
                print("\033c")
            elif dir_choice in ('n','no','q','quit'):
                print("\033c")
                return
            elif dir_choice in ('yes','y'):
                break
        while True:
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askdirectory()
            if path == '':
                print("\033c")
                return
            try:
                temp = TemporaryFile(dir = path)
                temp.close()
            except PermissionError:
                print('Access Denied! Application does not have permission\
                       to access desired location!')
                os.chdir(self.home_dir)
                time.sleep(3)
                print("\033c")
                continue
            except FileNotFoundError:
                print('No such directory.:',path)
                os.chdir(self.home_dir)
                time.sleep(3)
                print("\033c")
                continue
            except FileExistsError:
                print('directory already exists:.',path)
                os.chdir(self.home_dir)
                time.sleep(3)
                print("\033c")
                continue
            files_to_check = [i for i in os.listdir(self.home_dir) if i in os.listdir(path)]
            print('Move Files from:', self.home_dir,)
            print('To:',path,'?')
            move_input = ''.join(input('>>> ').split()).lower()
            if move_input in ('y','yes'):
                print("\033c")
                if len(files_to_check) > 0:
                    overwrite = self.overwrite_check(files_to_check,path) 
                for obj in tqdm(os.listdir()):
                    if obj not in files_to_check:
                        shutil.move(obj, path)
                    elif overwrite ==  True:
                        shutil.rmtree(os.path.join(path,obj))
                        shutil.move(obj,path)
                        print('Files Successfully moved to:',path)
                        time.sleep(1)
                        break
            elif move_input in ('n','no'):
                print('Directory Change successful')
                time.sleep(2)
                break
            else:
                print('Invalid Entry!')
                time.sleep(1)
                print("\033c")
        maskinput('Press Enter To Continue')
        self.home_dir = path
        self.update_config()
        os.chdir(self.home_dir)
        print("\033c")
        
  
    def start_up_clean(self):
        """ """
        if self.last_dir is not None:
            try:
                list_ = [i for i in os.listdir(self.last_dir) if self.last_chapter_name in i]
                if len(list_) > 0:
                    for i in list_:
                        path = os.path.join(self.last_dir,i)
                        os.remove(path)
                self.last_dir = None
                self.last_chapter_name = None
                self.update_config()
            except FileNotFoundError:
                self.last_dir = None
                self.last_chapter_name = None
                self.update_config()
        else:
            return
                
    def home(self):
        """Loads the pull list json file as well as
           loads all href links from into the book_lib
           dictionary, shows the text title and menu and waits for user input"""
           
        self.load_pull() #Gets contents of pull_list.config
        self.library_load() #Gets all links from site and loads them into dictionary.
        self.start_up_clean()#Cleans up any half downloaded files from previous uses
        while True:
            print('#'*32)
            print('#Read Comics.net Cbz Downloader#')
            print('#'*32)
            print('Support Your Local Comic Shop!')
            print('{} - {}'.format(self.day,self.todays_date.strftime('%B %d, %Y')))
            print('\nTotal Library count:{}'.format(len(self.book_lib)))
            print()
            print('A)Pull List.')
            print('B)Edit Pull List.')
            print('C)Library')
            print('D)Options')
            print('E)Open Home Folder')
            print('F)Go to Readcomics(Opens Browser)')
            print('Q)Quit.')
            choice = ''.join(input('>>> ').split()).lower()  
            if choice == 'q':
                break
            elif choice == 'a':
                self.download_pull_list()
            elif choice == 'b':
                self.edit_pull_list()
            elif choice == 'c':
                self.library_search()
            elif choice == 'd':
                self.options()
            elif choice == 'e':
                print('Opening Folder.')
                time.sleep(1)
                os.system('xdg-open "%s"' % self.home_dir)
                print("\033c")
            elif choice == 'f':
                print('Opening Browser.')
                webbrowser.open('http://readcomics.io')
                print("\033c")
            else:
                print('Invalid Entry!')
                time.sleep(1)
                print("\033c")

def main():
    comicApp = GetComic()
    os.chdir(comicApp.home_dir)
    print("\033c")
    comicApp.home()
    comicApp.update_config()
    print('\nGood Bye!\n')
    

if __name__ == '__main__':
    main()
  
