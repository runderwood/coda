import os
import re
import urllib
import urllib2
import urlparse

from BeautifulSoup import BeautifulSoup as BSoup
from codalib import APP_AUTHOR
from codalib.bagatom import wrapAtom, ATOM, ATOM_NSMAP, BAG, BAG_NSMAP
from datetime import datetime
from lxml import etree
from pypairtree import pairtree

from . import exceptions
from coda_mdstore.models import Bag, Bag_Info, Node, External_Identifier


pairtreeCandidateList = [
    "http://example.com/data3/coda-001/store/pairtree_root/",
    "http://example.com/data4/coda-002/store/pairtree_root/",
]
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml/"
XHTML = "{%s}" % XHTML_NAMESPACE
XHTML_NSMAP = {None: XHTML_NAMESPACE}


def getFileList(url):
    """
    Use BeautifulSoup to get a List of Files
    """

    fileList = []
    handle = urllib2.urlopen(url)
    soup = BSoup(handle)
    trList = soup.findAll('tr')
    for tr in trList:
        tds = tr.findAll('td')
        for td in tds:
            anchors = td.findAll('a')
            for anchor in anchors:
                try:
                    # if anchor.contents and "Parent Directory" in contents:
                    if anchor['href'][-1] == "/":
                        continue
                    fileList.append(anchor['href'])
                except Exception, e:
                    raise e
    return fileList


def getFileHandle(codaId, codaPath):
    """
    Attempt to get a urllib2 handle that we can read from based on a file
    specification
    """

    codaSplit = re.compile(r"ark:/\d+?/")
    codaPart = codaSplit.split(codaId, 1)[1]
    codaPairtree = pairtree.toPairTreePath(codaPart)
    codaPathParts = codaPath.split("/")
    for i in range(len(codaPathParts)):
        part = codaPathParts[i]
        codaPathParts[i] = urllib.quote(part)
    escapedCodaPath = "/".join(codaPathParts)
    nodeList = Node.objects.all()
    urlList = []
    exceptionList = []
    for node in nodeList:
        url_parts = urlparse.urlparse(node.node_url)
        url = urlparse.urljoin(
            "http://%s" % url_parts.hostname,
            os.path.join(
                url_parts.path,
                "store/pairtree_root",
                codaPairtree,
                codaPart,
                escapedCodaPath,
            )
        )
        # urlList.append(url)
        try:
            fileHandle = urllib2.urlopen(url)
            return fileHandle
        except Exception, e:
            exceptionList.append(str(e))
            pass
    raise Exception(
        "Unable to get handle for id %s at path %s" % (codaId, codaPath)
    )


def bagSearch(bagString):
    """
    Search across all of the field_body fields in the Bag_Info objects and
    return a list of related bags
    """

    bagList = Bag.objects.filter(
        bag_info__field_body__search=bagString).distinct()
    if not bagList:
        bagList = Bag.objects.filter(name__search=bagString)
    return bagList


def makeBagAtomFeed(bagObjectList, id, title):
    """
    Given an iterable of bags, make an ATOM feed xml representation of it
    """

    feedTag = etree.Element(ATOM + "feed", nsmap=ATOM_NSMAP)
    idTag = etree.SubElement(feedTag, ATOM + "id")
    idTag.text = id
    titleTag = etree.SubElement(feedTag, ATOM + "title")
    titleTag.text = title
    updatedTag = etree.SubElement(feedTag, ATOM + "updated")
    linkTag = etree.SubElement(feedTag, ATOM + "link")
    linkTag.set("rel", "self")
    linkTag.set("href", id)
    for bagObject in bagObjectList:
        entryTag = wrapAtom(
            objectsToXML(bagObject), bagObject.name, bagObject.name
        )
        feedTag.append(entryTag)
    return feedTag


def updateBag(request):
    """
    updates a bag record with new information from an xml file
    """

    xmlText = request.body
    entryRoot = None
    entryRoot = etree.XML(xmlText)
    contentElement = entryRoot.xpath("*[local-name() = 'content']")[0]
    codaXML = contentElement.xpath("*[local-name() = 'codaXML']")[0]
    bag_name = codaXML.xpath("*[local-name() = 'name']")[0].text.strip()

    if bag_name not in request.path:
        raise exceptions.BadBagName('The bag name supplied in the URL does not match the XML')

    bag = Bag.objects.get(name=bag_name)

    # delete old info objects
    old_bag_infos = Bag_Info.objects.filter(bag_name=bag)
    old_bag_infos.delete()
    # delete old external id objects
    old_ext_ids = External_Identifier.objects.filter(belong_to_bag=bag)
    old_ext_ids.delete()
    # attempt to update a Bag object from the codaXML section
    bagObject, bagInfoObjectList, errorCode = xmlToBagObject(codaXML)
    bagObject.save()
    for bagInfoObject in bagInfoObjectList:
        bagInfoObject.save()
    return bagObject


def createBag(xmlText):
    """
    creates a bag from an xml document. returns a bag.
    """

    entryRoot = None
    entryRoot = etree.XML(xmlText)
    if entryRoot == None:
        raise Exception("Unable to parse uploaded XML")
    contentElement = entryRoot.xpath("*[local-name() = 'content']")[0]
    if contentElement == None:
        raise Exception("No content element located")
    codaXML = contentElement.xpath("*[local-name() = 'codaXML']")[0]
    codaName = codaXML.xpath("*[local-name() = 'name']")[0].text.strip()
    oldBagInfoObjectList = Bag_Info.objects.filter(bag_name=codaName)
    for oldBagInfoObject in oldBagInfoObjectList:
        oldBagInfoObject.delete()
    # attempt to create a Bag object from the codaXML section
    bagObject, bagInfoObjectList, errorCode = xmlToBagObject(codaXML)
    if errorCode:
        raise Exception("codaXML issue, %s" % (errorCode,))
    bagObject.save()
    for bagInfoObject in bagInfoObjectList:
        bagInfoObject.save()
    return bagObject, bagInfoObjectList


def xmlToBagObject(codaXML):
    """
    Take a codaXML element and turn it into a Bag object
    Returns (Bag object, list of Bag_Info objects, error code)
    """

    # first, let's get the bag name and see if it exists already
    try:
        name = codaXML.xpath("*[local-name() = 'name']")[0].text.strip()
        bagObject = Bag.objects.get(Bag, name=name)
    # if we can't get the object, then we're just making a new one.
    except Exception, e:
        bagObject = Bag()
    dateFormatString = "%Y-%m-%d"
    try:
        bagObject.name = codaXML.xpath(
            "*[local-name() = 'name']")[0].text.strip()
    except:
        return (None, None, "Unable to set 'name' attribute")
    try:
        bagObject.files = codaXML.xpath(
            "*[local-name() = 'fileCount']")[0].text.strip()
    except:
        return (None, None, "Unable to set 'files' attribute")
    try:
        bagObject.size = int(codaXML.xpath(
            "*[local-name() = 'payloadSize']")[0].text.strip())
    except Exception, e:
        return (None, None, "Unable to set 'size' attribute: %s" % (e,))
    try:
        bagObject.bagit_version = codaXML.xpath(
            "*[local-name()='bagitVersion']")[0].text.strip()
    except:
        pass
    try:
        bagObject.last_verified_date = datetime.strptime(
            codaXML.xpath(
                "*[local-name() = 'lastVerified']"
            )[0].text.strip(), dateFormatString
        )
    except:
        bagObject.last_verified_date = datetime.now()
    try:
        bagObject.last_verified_status = codaXML.xpath(
            "*[local-name() = 'lastStatus']")[0].text.strip()
    except:
        bagObject.last_verified_status = "pass"
    try:
        bagObject.bagging_date = datetime.strptime(
            codaXML.xpath(
                "*[local-name() = 'baggingDate']"
            )[0].text.strip(), dateFormatString
        )
    except:
        bagObject.bagging_date = datetime.now()
    bagInfo = codaXML.xpath("*[local-name() = 'bagInfo']")[0]
    if len(bagInfo):
        items = bagInfo.xpath("*[local-name() = 'item']")
    # make a list to store all the bag_info objects
    bagInfoObjects = []
    # iterate through items
    for item in items:
        bagInfoObject = Bag_Info()
        bagInfoObject.bag_name = bagObject
        try:
            bagInfoObject.field_name = item.xpath(
                "*[local-name() = 'name']")[0].text.strip()
            bagInfoObject.field_body = item.xpath(
                "*[local-name() = 'body']")[0].text.strip()
            if bagInfoObject.field_name == 'External-Identifier':
                extID = External_Identifier(
                    value=bagInfoObject.field_body,
                    belong_to_bag=bagInfoObject.bag_name,
                )
                extID.save()
        except:
            continue
        bagInfoObjects.append(bagInfoObject)
    return (bagObject, bagInfoObjects, None)


def objectsToXML(bagObject):
    """
    This is the reverse of xmlToObjects.  Given a "Bag" object, and a list of
    Bag_Info objects, it generates an XML object representative of such in the
    'codaXML' format.
    """

    codaXML = etree.Element(BAG + "codaXML", nsmap=BAG_NSMAP)
    name = etree.SubElement(codaXML, BAG + "name")
    name.text = bagObject.name
    fileCount = etree.SubElement(codaXML, BAG + "fileCount")
    fileCount.text = str(bagObject.files)
    payLoadSize = etree.SubElement(codaXML, BAG + "payloadSize")
    payLoadSize.text = str(bagObject.size)
    bagitVersion = etree.SubElement(codaXML, BAG + "bagitVersion")
    bagitVersion.text = bagObject.bagit_version
    try:
        lastVerified = etree.SubElement(codaXML, BAG + "lastVerified")
        lastVerified.text = str(bagObject.last_verified_date)
        lastStatus = etree.SubElement(codaXML, BAG + "lastStatus")
        lastStatus.text = bagObject.last_verified_status
    except:
        pass
    bagInfo = etree.SubElement(codaXML, BAG + "bagInfo")
    bagInfoObjectList = Bag_Info.objects.filter(bag_name=bagObject)
    for bagInfoObject in bagInfoObjectList:
        item = etree.SubElement(bagInfo, BAG + "item")
        nameTag = etree.SubElement(item, BAG + "name")
        nameTag.text = bagInfoObject.field_name
        bodyTag = etree.SubElement(item, BAG + "body")
        bodyTag.text = bagInfoObject.field_body
    return codaXML


def nodeEntry(node, webRoot=None):
    """
    Form an atom xml for a given node object.
    """

    nodeXML = etree.Element("node")
    node_name = etree.SubElement(nodeXML, "name")
    node_name.text = node.node_name
    node_capacity = etree.SubElement(nodeXML, "capacity")
    node_capacity.text = str(node.node_capacity)
    node_size = etree.SubElement(nodeXML, "size")
    node_size.text = str(node.node_size)
    node_path = etree.SubElement(nodeXML, "path")
    node_path.text = node.node_path
    node_url = etree.SubElement(nodeXML, "url")
    node_url.text = node.node_url
    node_last_checked = etree.SubElement(nodeXML, "last_checked")
    node_last_checked.text = str(node.last_checked)
    atomXML = wrapAtom(
        xml=nodeXML,
        id='http://%s/node/%s/' % (webRoot, node.node_name),
        title=node.node_name,
        author=APP_AUTHOR['name'],
        author_uri=APP_AUTHOR['uri'],
    )
    return atomXML


def updateNode(request):
    """
    Parse the XML in a PUT request and update the node stat based on that
    """

    nodeXML = request.body
    entryRoot = etree.fromstring(nodeXML)
    contentElement = entryRoot.xpath("*[local-name() = 'content']")[0]
    nodeXML = contentElement.xpath("*[local-name() = 'node']")[0]
    node_name = nodeXML.xpath("*[local-name() = 'name']")[0].text.strip()

    if node_name not in request.path:
        raise exceptions.BadNodeName('The node name supplied in the URL does not match the XML')

    node = Node.objects.get(node_name=node_name)

    # we need capacity and size
    node_capacity = nodeXML.xpath(
        "*[local-name() = 'capacity']"
    )[0].text.strip()
    node_size = nodeXML.xpath("*[local-name() = 'size']")[0].text.strip()
    node_path = nodeXML.xpath("*[local-name() = 'path']")[0].text.strip()
    node_url = nodeXML.xpath("*[local-name() = 'url']")[0].text.strip()
    node.node_capacity = long(node_capacity)
    node.node_size = long(node_size)
    node.node_path = node_path
    node.node_name = node_name
    node.node_url = node_url
    # last_checked most likely will be passed in via the GET > PUT discussions
    # but will always be overwritten.
    node.last_checked = datetime.now()
    return node


def createNode(request):
    """
    Parse the XML in a POST request and create the node stat based on that
    """

    nodeXML = request.body
    entryRoot = etree.fromstring(nodeXML)
    contentElement = entryRoot.xpath("*[local-name() = 'content']")[0]
    nodeXML = contentElement.xpath("*[local-name() = 'node']")[0]
    node_name = nodeXML.xpath("*[local-name() = 'name']")[0].text.strip()
    node_capacity = nodeXML.xpath(
        "*[local-name() = 'capacity']"
    )[0].text.strip()
    node_size = nodeXML.xpath("*[local-name() = 'size']")[0].text.strip()
    node_path = nodeXML.xpath("*[local-name() = 'path']")[0].text.strip()
    node_url = nodeXML.xpath("*[local-name() = 'url']")[0].text.strip()
    node = Node()
    node.node_capacity = long(node_capacity)
    node.node_size = long(node_size)
    node.node_path = node_path
    node.node_name = node_name
    node.node_url = node_url
    node.last_checked = datetime.now()
    return node
