# Specify7-Api-Demo

> ⚠️ The code within this repository is not meant for production or finalized environments: it exists solely to demonstrate some of the capabilities of the Specify 7 API. Proceed with caution if you wish to use the application as-is or with very slight modifications to accomplish tasks it was not specifically designed to accomplish
> 
> The code can, however, be used as inspiration or a starting place for other developmental projects

The repository exists to provide a working demonstration of using the [Specify 7](https://github.com/specify/specify7) API for a practical application. 
For additional information about the API, view the related documentaion of the API [on the Specifourm](https://discourse.specifysoftware.org/t/how-to-use-the-specify-api-as-a-generic-webservice/181) or on the [Specify 7 GitHub Wiki](https://github.com/specify/specify7/wiki/API-Documentation-Demo).

### Demonstration Motivation
Currently in Specify 7, there is not an easy way using the frontend interface (or the WorkBench component) to mass-import synonymized Taxa. 
The goal of this demo is to develop an application which will read a csv file containing simple taxonomic information and upload the taxa if they do not already exist in the Specify 7 instance. If any taxon already does exist, we will update it to match the information in the csv. 

Specifically, we are in charge of uploading mammal taxa records from a csv. 

Consider the [taxon_to_import.csv](https://github.com/melton-jason/Specify7-Api-Demo/blob/main/taxon_to_import.csv), which contains the information we wish to upload. 

 (All taxa information was adopted from [gbif.org](https://www.gbif.org/))

 Rows in our csv can have one of two forms. If the taxon is accepted (contains 'Yes' for isAccepted), then it will not contain any information in the `AcceptedGenus`, `AcceptedSpecies`, and `AcceptedAuthor` columns. 
 Otherwise if the taxon is a synonym, it will _always_ contain information in the `AcceptedGenus`, `AcceptedSpecies`, and `AcceptedAuthor` columns.

 The `Author` and `AccecptedAuthor` columns only represent the taxon authors for Species and AcceptedSpecies (respectively).  

For example, here are the first 2 rows of the [taxon_to_import.csv](https://github.com/melton-jason/Specify7-Api-Demo/blob/main/taxon_to_import.csv), which exhibit the differences described above. 

| Order        | Family      | Genus      | Species   | isAccepted | Author                    | AcceptedGenus | AcceptedSpecies | AcceptedAuthor         |
|--------------|-------------|------------|-----------|------------|---------------------------|---------------|-----------------|------------------------|
| Afrosoricida | Tenrecidae  | Microgale  | talazaci  | Yes        | Major, 1896               |               |                 |                        |
| Afrosoricida | Tenrecidae  | Oryzorictes| talpoides | No         | G.Grandidier & Petit, 1930| Oryzorictes  | hova            | A.Grandidier, 1870     |

Our application should handle a row in the CSV following way: 
- For each specified rank in [Order, Family, Genus, Species], we check to see if a Taxon record at the rank exists with the name and has a parent with a name equal to the name of the taxon in the previous rank in the row (the previous Taxon record for Order is the Taxon record with rank Class called 'Mammalia')
  - For example, in the first row we check to see if Taxon record with name 'Afrosoricida' at the Order rank exists who is a child of Mammalia. Then we proceed with the below steps and then check if there is a Taxon record at the Family rank with name 'Tenrecidae' which is a child of 'Afrosoricida', ...
- If the Taxon record exists, we fetch the record to use it for the next rank in the row. Otherwise, we create the Taxon record first and then can use it for the next rank in the row
- If the rank is 'Species', there are additional steps which need to be done:
  - If the row contains 'No' for 'isAccepted', we fetch or create the AcceptedSpecies Taxon (creating the AcceptedGenus if needed) and then synonymize the 'Species' to 'AcceptedSpecies'
  - If the Species or AcceptedSpecies records have information in the `author` field which does not match Author or AcceptedAuthor (respectively), then the taxon record is updated match the author


### Installing the Project
The project was developed and tested using `Python v3.12.3` and the Python library `requests v2.31.0`.

Other versions of Python and requests may work, but the behavior has not been explicitly verified. 

View more information about the requests library at [https://pypi.org/project/requests/](https://pypi.org/project/requests/). 

- Clone or otherwise copy the repository
- `cd` into the folder containing the repository to set it as the working directory
- Create a python virtual environment using `python3 -m venv .venv`
  - This creates a `.venv` folder in the working directory which contains the virtual environment   
- [Source the environment](https://docs.python.org/3/library/venv.html#how-venvs-work)
- Install the dependencies using `pip3 install -r requirements.txt`

The demo can then be run (while the virtual environment is sourced) using `python3 main.py`

### Using the Demo
Currently, the demo uploads the taxonomic information to the Specify 7 demo instance at [https://sp7demofish.specifycloud.org/specify/](https://sp7demofish.specifycloud.org/specify/) using user `sp7demofish` (which has password `sp7demofish`) logged in to the `KUFishvoucher` collection. 

https://github.com/melton-jason/Specify7-Api-Demo/blob/2de14c5af6fa8e1856e4e02497be54224728bdb1/main.py#L32-L35

While running the demo, each network request made with the API (and any request payload, when applicable) along with the timestamp is logged and saved into a `importlog.txt` file. 

The general steps and progess (primarily which row is being processed from the CSV) is printed to the standard output. 

Every taxon record created through the demo will have `"Generated in Demo"` inserted into the remarks field. 

Alongside creating and updating Taxon records, a Taxon recordset called `Imported Species (Api Demo)` is created (owned by the user which was logged in and created in the logged in collection) containing all of the species records which were fetched, updated, or created for easy viewing in the application once the demo completes. 
