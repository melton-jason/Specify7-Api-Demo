import os
import csv
import logging

from typing import TypedDict, Literal, Optional, Dict, List, Callable

from session import Session, extract_id_from_uri, construct_api_link
from taxon_helpers import TAXON_TABLE_ID, RANK_NAME, Discipline_Record, Taxon_Record, TaxonTreeDefItem_Record, get_defitem, get_taxon, update_author, create_accepted_taxon

LOG_FILE_NAME = "importlog.txt"

"""
Some globals which we can assume will not be modified for the duration of the 
script once initially fetched.
"""

MAMMALIA = None
TREE_DEF_ID = None

DEF_ITEMS: Dict[RANK_NAME, Optional[TaxonTreeDefItem_Record]] = {
    "Order": None,
    "Family": None,
    "Genus": None,
    "Species": None
}


def main():
    logging.basicConfig(filename=LOG_FILE_NAME, format='%(asctime)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

    s = Session(domain="https://sp7demofish.specifycloud.org")
    collection_id = s.get_collection_id("KUFishvoucher")
    s.login(username="sp7demofish", password="sp7demofish",
            collection_id=collection_id)

    discipline = s.fetch_resource('discipline', s.get_domain_id('Discipline'))

    fetch_tree_info(s, discipline)

    rows = deserialize_csv("taxon_to_import.csv")

    taxon_ids = [proccess_row(s, row) for row in rows]

    print(f"Creating 'Imported Species (Api Demo)' recordset with results")
    recordset_data = {
        "collectionmemberid": s.get_domain_id('Collection'),
        "dbtableid": TAXON_TABLE_ID,
        "name": "Imported Species (Api Demo)",
        "type": 0,
        "version": 0,
        "specifyuser": s.specifyuser['resource_uri']
    }
    record_set = s.create_resource('recordset', recordset_data)

    for taxon_id in taxon_ids:
        recordsetitem_data = {
            "recordid": taxon_id,
            "recordset": record_set["resource_uri"]
        }
        s.create_resource('recordsetitem', recordsetitem_data)

    print(f"Generated logs available at {os.path.abspath(LOG_FILE_NAME)}")


def fetch_tree_info(session: Session, discipline: Discipline_Record):
    global TREE_DEF_ID, MAMMALIA, DEF_ITEMS

    TREE_DEF_ID = extract_id_from_uri(discipline['taxontreedef'])
    class_def_item = get_defitem(session, TREE_DEF_ID, "Class")
    MAMMALIA = get_taxon(session, "Mammalia", class_def_item["id"])
    if MAMMALIA is None:
        phylum_def_item = get_defitem(session, TREE_DEF_ID, 'Phylum')
        chordata = get_taxon(session, 'Chordata', phylum_def_item["id"])
        MAMMALIA = create_accepted_taxon(
            session, class_def_item, 'Mammalia', chordata)

    DEF_ITEMS["Order"] = get_defitem(session, TREE_DEF_ID, "Order")
    DEF_ITEMS["Family"] = get_defitem(session, TREE_DEF_ID, "Family")
    DEF_ITEMS["Genus"] = get_defitem(session, TREE_DEF_ID, "Genus")
    DEF_ITEMS["Species"] = get_defitem(session, TREE_DEF_ID, "Species")
    print("Fetched tree items")


class Row(TypedDict):
    Order: str
    Family: str
    Genus: str
    Species: str
    isAccepted: Literal['Yes', 'No']
    Author: str
    AcceptedGenus: str
    AcceptedSpecies: str
    AcceptedAuthor: str


def deserialize_csv(file_name) -> List[Row]:
    results = []
    with open(file_name, "r") as file:
        for line in csv.DictReader(file):
            new_line = {}
            for col, data in line.items():
                new_line[col.strip()] = data.strip()
            results.append(new_line)

    return results


def tree_info_fetched(func: Callable):
    """Decorator which ensures that the globals which store information related
    to commonly used tree-structure contain values
    """
    def wrapped(*args, **kwargs):
        all_tree_items = [MAMMALIA, TREE_DEF_ID] + list(DEF_ITEMS.values())
        fetched = all(
            False if tree_info is None else True for tree_info in all_tree_items)
        if not fetched:
            raise Exception("Tree info must be initialized", all_tree_items)
        return func(*args, **kwargs)

    return wrapped


@tree_info_fetched
def proccess_row(session: Session, row: Row) -> int:
    """Processes a single row in the CSV, creating/updating any Taxon records
    when necessary and finally returning the id of the lowest rank (Species) 
    which were fetched/updated/created 
    """
    print(f"Processing row: {row}")
    # because we go sequentially down the ranks, the parent node of all Order
    # rank nodes we wish to upload will be Mammalia
    parent_taxon = MAMMALIA

    # for each rank in a row, fetch or create the record at the rank
    for rank_name in DEF_ITEMS.keys():
        taxon = get_or_create_taxon(session, row, rank_name, parent_taxon)
        parent_taxon = taxon

    return taxon['id']


@tree_info_fetched
def get_accepted(session: Session, row: Row) -> Optional[str]:
    """Return the resource_uri for the accepted taxon
    of a synonymized node. 
    If the accepted Genus or accepted Species do not exist, create them when
    needed. 

    """
    # the resource_uri for an already accepted node is None
    if row["isAccepted"] == 'Yes':
        return None

    accepted = get_taxon(
        session, row["AcceptedSpecies"], DEF_ITEMS["Species"]["id"], row["AcceptedGenus"])

    # if the species exists, update the author and directly return the species
    if accepted is not None:
        updated = update_author(session, accepted, row["AcceptedAuthor"])
        return updated['resource_uri']

    accepted_genus = get_taxon(
        session, row["AcceptedGenus"], DEF_ITEMS["Genus"]["id"])
    if accepted_genus is None:
        # if the accepted species does not exist, upload it as a child of a
        # node with name "Uploaded" at the Family rank
        parent = get_taxon(session, 'Uploaded',
                           DEF_ITEMS["Family"]["id"], 'Uploaded')
        accepted_genus = create_accepted_taxon(
            session, DEF_ITEMS['Genus'], row["AcceptedGenus"], parent)

    new_accepted_species = create_accepted_taxon(session,
                                                 DEF_ITEMS['Species'], row["AcceptedSpecies"], accepted_genus, row['AcceptedAuthor'])
    return new_accepted_species['resource_uri']


@tree_info_fetched
def get_or_create_taxon(session: Session, row: Row, rank_name: RANK_NAME, parent_taxon: Taxon_Record) -> Taxon_Record:
    """ Attempt to fetch the taxon with with the name specified at <rank_name> 
    in the <row>.
    If needed, update the taxon record (such as author or synonymizing) to 
    match the information in the <row>. 

    If the taxon does not exist, then create it. 
    """
    rank = DEF_ITEMS[rank_name]
    taxon = get_taxon(session, row[rank_name],
                      rank["id"], parent_taxon["name"])

    # we only want to synonymize and change author if at the Species rank
    isAccepted = row["isAccepted"] == 'Yes' and rank_name == 'Species'
    author = row["Author"] if rank_name == "Species" else None

    if taxon is not None:
        # if the existing taxon is at the Species level and is accepted but
        # synonymized in the csv, then synonymize it
        if rank_name == 'Species' and taxon['isaccepted'] == True and isAccepted == False:
            taxon = synonymize_taxon(session, row, taxon)
        return taxon if author is None else update_author(session, taxon, author)

    taxon_data = {
        # fullname generated by backend when saved
        "name": row[rank_name],
        "author": author,
        "acceptedtaxon": get_accepted(session, row) if rank_name == 'Species' else None,
        "isaccepted": isAccepted,
        "ishybrid": False,
        "rankid": rank["rankid"],
        "version": 0,
        "remarks": "Generated in Demo",
        "definition": construct_api_link("taxontreedef", TREE_DEF_ID),
        "definitionitem": rank["resource_uri"],
        "parent": parent_taxon["resource_uri"]
    }
    taxon = session.create_resource("taxon", taxon_data)

    return taxon


@tree_info_fetched
def synonymize_taxon(session: Session, row: Row, taxon: Taxon_Record) -> Taxon_Record:
    accepted_uri = get_accepted(session, row)

    updated_fields = {
        "isaccepted": False,
        "acceptedtaxon": accepted_uri
    }
    return session.update_resource('taxon', taxon["id"], updated_fields)


if __name__ == "__main__":
    main()
