from typing import Optional, Literal, Type

from session import Session, SERIALIZED_RECORD

# from the Specify 6 /config/specify_tableid_listing.xml file
# needed to create a record set
TAXON_TABLE_ID = 4

# Type which corresponds to the literal string values of the ranks in the CSV
RANK_NAME = Literal[
    'Order',
    'Family',
    'Genus',
    'Species'
]

# Type aliases for commonly used tables in the application
Discipline_Record = Type[SERIALIZED_RECORD]
Taxon_Record = Type[SERIALIZED_RECORD]
TaxonTreeDefItem_Record = Type[SERIALIZED_RECORD]


def get_defitem(session: Session, tree_def_id: int, rank_name: RANK_NAME) -> TaxonTreeDefItem_Record:
    """Returns the serialized taxontreedefitem defined with <rank_name> on a 
    given TaxonTreeDef with id <tree_def_id>
    """
    ranks = session.fetch_collection(
        f'/api/specify/taxontreedefitem/?name={rank_name}&treedef={tree_def_id}')
    if len(ranks) == 0:
        raise Exception(f"No taxontreedefitems with name {rank_name}")
    return ranks[0]


def get_taxon(session: Session, name: str, tree_def_item_id: int, parent_name: Optional[str] = None) -> Optional[Taxon_Record]:
    """Returns the serialized Taxon record which has name <name> with the 
    taxontreedefitem <tree_def_item_id>

    If <parent_name> is provided, further restrict the search to only include 
    Taxon records of the rank and name with parent's of name <parent_name>

    If no Taxon record was found matching the critera, return None
    """
    parent_query = '' if parent_name is None else f'&parent__name={
        parent_name}'

    taxons = session.fetch_collection(
        f'/api/specify/taxon/?name={name}&definitionitem={tree_def_item_id}{parent_query}')
    if len(taxons) == 0:
        return None

    return taxons[0]


def update_author(session: Session, taxon: Taxon_Record, author: str) -> Taxon_Record:
    """Given a serialized Taxon record <taxon>, and a string representing an 
    author, update the <taxon> record to have author <author>
    """
    if taxon['author'] == author:
        return taxon
    return session.update_resource('taxon', taxon['id'], {"author": author})
