"""
Model exported as python.
Name : modello
Group : 
With QGIS : 31202
"""
from xml.dom.minidom import parse
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterString
from qgis.core import QgsProcessingParameterBoolean
from qgis.core import QgsVectorLayer
import processing
import xml.dom.minidom

TAG_ROOT = "esri:Workspace"
TAG_WORKSPACE_DEF = "WorkspaceDefinition"
TAG_DATASETDEFINITIONS = "DatasetDefinitions"
TAG_DE = "DataElement"
TAG_DE_NAME = "Name"
TAG_DE_TYPE = "DatasetType"
TAG_DE_FIELDS = "Fields"
TAG_DE_FIELDS_ARR = "FieldArray"
TAG_DE_FIELD = "Field"
TAG_DE_FIELD_NAME = "Name"
TAG_DE_FIELD_TYPE = "Type"
TAG_DE_FIELD_ISNULL = "IsNullable"
TAG_DE_FIELD_LENGTH = "Length"
TAG_DE_FIELD_PRECISION = "Precision"
TAG_DE_FIELD_SCALE = "Scale"
TAG_DE_FIELD_DOMAIN = "Domain"
TAG_DE_FIELD_DOMAIN_NAME = "DomainName"
TAG_DE_SUBTYPE = "SubtypeFieldName"
TAG_DE_SUBTYPE_DEF = "DefaultSubtypeCode"
TAG_DE_SUBTYPES = "Subtypes"
TAG_DE_SUBTYPES_SUBTYPE = "Subtype"
TAG_DE_GEOM_DEF = "GeometryDef"
TAG_DE_GEOM_TYPE = "GeometryType"
TAG_DE_GEOM_Z = "HasZ"
TAG_DE_GEOM_M = "HasM"
TAG_DE_GEOM_SPATIAL_REF = "SpatialReference"
TAG_DE_GEOM_WKID = "WKID"

#https://doc.arcgis.com/en/insights/latest/get-started/supported-types-from-databases.htm
#https://www.postgresqltutorial.com/postgresql-data-types/
class Field():

    def __init__(self):
        self.domain = None
        self.name = None
        self.type = None
        self.isnull = True
        self.length = None
        self.precision = None
        self.scale = None
        self.geom_def = None
        self.default = None
        self.serial = False

    def is_valid(self):
        if self.name is not None and self.to_pg_type() is not None:
            if self.name.lower() not in ('shape_length','shape_area','globalid'):
                return True
        return False

    def is_geometry(self):
        return self.name.lower() == 'shape' and self.type == "esriFieldTypeGeometry"

    def to_pg_type(self):
        if self.type == "esriFieldTypeSmallInteger": 
            return "SMALLINT"
        elif self.type=="esriFieldTypeInteger":
            return "INTEGER"
        elif self.type in ("esriFieldTypeDouble", "esriFieldTypeSingle"):    
            if self.precision==0 and self.scale==0:        
                if self.type=="esriFieldTypeDouble":
                    return "DOUBLE PRECISION"
                elif self.type=="esriFieldTypeSingle":    
                    return "REAL"
            else:
                return "NUMERIC(%s, %s)" % (str(self.precision), str(self.scale))
        elif self.type=="esriFieldTypeString":
            leng = 255
            if self.length is not None:
                leng = self.length
            return "VARCHAR(%s)" % (str(leng),)
        elif self.type=="esriFieldTypeDate":
            return "TIMESTAMP"
        elif self.type=="esriFieldTypeOID":
            return "BIGINT"
        elif self.type=="esriFieldTypeGlobalID":
            return "VARCHAR(32)"
        else:
            return None

    def geom_info(self):
        ret = { 'type': "POINT", 'dim': 2, 'epsg': 4326 }
        g_type = self.geom_def.getElementsByTagName(TAG_DE_GEOM_TYPE)[0].childNodes[0].data
        type == "POINT"
        if g_type=="esriGeometryPolygon":
            ret["type"] = "MULTIPOLYGON"
        elif g_type=="esriGeometryPolyline":
            ret["type"] = "MULTILINESTRING"
        elif g_type == "esriGeometryMultiPoint":
            ret["type"] = "MULTIPOINT"
        g_z = self.geom_def.getElementsByTagName(TAG_DE_GEOM_Z)[0].childNodes[0].data
        g_m = self.geom_def.getElementsByTagName(TAG_DE_GEOM_M)[0].childNodes[0].data
        if g_z == "true":
            ret["dim"] += 1
        if g_m == "true":
            ret["dim"] += 1
        g_srs = self.geom_def.getElementsByTagName(TAG_DE_GEOM_SPATIAL_REF)[0]  
        ret["epsg"] = int(g_srs.getElementsByTagName(TAG_DE_GEOM_WKID)[0].childNodes[0].data)      
        return ret

    def has_domain(self):
        return self.domain is not None

    def __str__(self):        
        if self.serial:
            sql = self.name.lower() + " SERIAL"
        else:        
            s_null = "NOT NULL"
            if self.isnull == "true":
                s_null = "NULL"
            s_default = ""
            if self.default is not None:
                if self.type=="esriFieldTypeString":
                    s_default = "DEFAULT '%s'" % (self.default.replace("'", "''"),)
                else:
                    s_default = "DEFAULT %s" % (self.default,)
            sql = "%s %s %s %s" % (self.name.lower(), self.to_pg_type(), s_null, s_default)
        return sql


class FeatureClass():
    
    def __init__(self, name, oid = None, sub_type=None, sub_type_default = None, schema='public'):
        self.schema = schema
        self.name = name
        self.oid = oid
        if sub_type=='':
            sub_type = None
            sub_type_default = None
        self.sub_type = sub_type
        self.sub_type_default = sub_type_default
        self.fields = []  
        self.geom = None  
        self.subtypes = []    
    
    def add_field(self, field):
        if field.name == self.sub_type:
            field.default = self.sub_type_default
        if self.oid is not None and field.name.lower() == self.oid.lower():
            field.serial = True
        if field.is_geometry():
            self.geom = field
        else:
            self.fields.append(field)

    def list_fields(self):
        list = ", ".join([f.name.lower() for f in self.get_valid_fields()])
        if self.geom is not None:
            list += ", geom"
        return list
        
    def set_subtypes(self, subs):
        for sub in subs:
            name = sub.getElementsByTagName("SubtypeName")[0].childNodes[0].data
            code = sub.getElementsByTagName("SubtypeCode")[0].childNodes[0].data
            info = []
            f_info = sub.getElementsByTagName("FieldInfos")[0].getElementsByTagName("SubtypeFieldInfo")
            for f in f_info:
                f_name = f.getElementsByTagName("FieldName")[0].childNodes[0].data
                d_name = f.getElementsByTagName("DomainName")[0].childNodes[0].data
                info.append({
                    "field": f_name,
                    "domain": d_name
                })
            self.subtypes.append({
                "name": name,
                "code": code,
                "info": info
            })
        
    def get_valid_fields(self):
        v_fields = []
        for f in self.fields:
            if f.is_valid():
                v_fields.append(f)
        return v_fields
        
    def get_domain_fields(self):
        v_fields = []
        for f in self.fields:
            if f.is_valid() and f.domain is not None:
                v_fields.append(f)
        return v_fields    
        
    def is_valid(self):
        if len(self.fields) > 0 and self.geom is not None:
            return True
        return False

    def __str__(self):
        table_name = self.schema.lower() + "." + self.name.lower()
        sql = "CREATE TABLE %s(\n   " % (table_name)
        sql += ",\n   ".join([str(f) for f in self.get_valid_fields()])
        if self.oid is not None:
            sql += ", "
            sql += "PRIMARY KEY("  + self.oid
            if self.sub_type is not None:
                sql += ", "  + self.sub_type
            sql += ") "
        sql += "\n)"
        if self.sub_type is not None:
            sql += " PARTITION BY LIST(%s)" % (self.sub_type,)
        sql += ";\n"
        
        if self.geom is not None:
            info = self.geom.geom_info()
            sql += "SELECT AddGeometryColumn ('%s', '%s', 'geom', %s, '%s', %s);\n" % (self.schema.lower(), self.name.lower(), str(info["epsg"]), info["type"], str(info["dim"]))
        if self.sub_type is None:
            cont = 0
            for f in self.get_domain_fields():
                cont += 1
                sql += "ALTER TABLE %s.%s ADD CONSTRAINT %s_FK_%s FOREIGN KEY(%s) REFERENCES %s.%s(CODE);\n" % (self.schema.lower(), self.name.lower(), self.name.lower(), str(cont), f.domain, self.schema.lower(), f.domain.lower())
        else:
            for s in self.subtypes:
                cont = 0
                partition_name = table_name + "_" + s["code"]
                p_name = self.name.lower() + "_" + s["code"]
                sql += "CREATE TABLE %s PARTITION OF %s FOR VALUES IN (%s);\n" % (partition_name, table_name, s["code"])
                for f in s["info"]:
                    cont += 1
                    sql += "ALTER TABLE %s ADD CONSTRAINT %s_FK_%s FOREIGN KEY(%s) REFERENCES %s.%s(CODE);\n" %(partition_name, p_name, str(cont), f["field"], self.schema.lower(), f["domain"])
        return sql


class KhrisXMLFeatureClassesImporterAlgorithm(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString('XMLPATH', 'XML Workspace Definition', multiLine=False, defaultValue=''))
        self.addParameter(QgsProcessingParameterString('GPKGPATH', 'GeoPackage', multiLine=False, defaultValue=''))
        self.addParameter(QgsProcessingParameterString('DBNAME', 'Pg Connection Name', multiLine=False, defaultValue='KRIHS'))
        self.addParameter(QgsProcessingParameterString('SCHEMA', 'Schema', multiLine=False, defaultValue='public'))
        self.addParameter(QgsProcessingParameterBoolean('DROPIFEXISTS', 'Drop if exists', optional=True, defaultValue=True))

    def getDatasets(self):
        DOMTree = xml.dom.minidom.parse(self.xml_path)
        collection = DOMTree.documentElement
        wrkDef = collection.getElementsByTagName(TAG_WORKSPACE_DEF)[0]
        datasetDefs = wrkDef.getElementsByTagName(TAG_DATASETDEFINITIONS)[0]
        dataset_list = datasetDefs.getElementsByTagName(TAG_DE)
        return dataset_list

    def getDatasetDef(self, data_element):
        type = data_element.getElementsByTagName(TAG_DE_TYPE)[0].childNodes[0].data
        subtypes = data_element.getElementsByTagName(TAG_DE_SUBTYPE)
        subtype = None
        subtype_def = None
        subs = []
        if len(subtypes)>0:
            subtype = data_element.getElementsByTagName(TAG_DE_SUBTYPE)[0].childNodes[0].data
            subtype_def = data_element.getElementsByTagName(TAG_DE_SUBTYPE_DEF)[0].childNodes[0].data
            subs = data_element.getElementsByTagName(TAG_DE_SUBTYPES)[0].getElementsByTagName(TAG_DE_SUBTYPES_SUBTYPE)
        
        if type == "esriDTFeatureClass":
            name = data_element.getElementsByTagName(TAG_DE_NAME)[0].childNodes[0].data
            oid = None
            has_oid = data_element.getElementsByTagName("HasOID")[0].childNodes[0].data
            if has_oid == "true":
                oid = data_element.getElementsByTagName("OIDFieldName")[0].childNodes[0].data
            feature_class = FeatureClass(name, oid, subtype, subtype_def, self.pg_schema)
            feature_class.set_subtypes(subs)
            fields = data_element.getElementsByTagName(TAG_DE_FIELDS)[0]
            fields_array = fields.getElementsByTagName(TAG_DE_FIELDS_ARR)[0]
            field_list = fields_array.getElementsByTagName(TAG_DE_FIELD)
            for field in field_list:
                fld = Field()
                fld.name = field.getElementsByTagName(TAG_DE_FIELD_NAME)[0].childNodes[0].data
                fld.type = field.getElementsByTagName(TAG_DE_FIELD_TYPE)[0].childNodes[0].data
                fld.isnull = field.getElementsByTagName(TAG_DE_FIELD_ISNULL)[0].childNodes[0].data
                fld.length = int(field.getElementsByTagName(TAG_DE_FIELD_LENGTH)[0].childNodes[0].data)
                fld.precision = int(field.getElementsByTagName(TAG_DE_FIELD_PRECISION)[0].childNodes[0].data)
                fld.scale = int(field.getElementsByTagName(TAG_DE_FIELD_SCALE)[0].childNodes[0].data)
                f_domain = field.getElementsByTagName(TAG_DE_FIELD_DOMAIN)
                domain_name = None
                if len(f_domain):
                    f_domain = f_domain[0]
                    domain_name = f_domain.getElementsByTagName(TAG_DE_FIELD_DOMAIN_NAME)[0].childNodes[0].data
                fld.domain = domain_name
                if fld.is_geometry():
                    fld.geom_def = field.getElementsByTagName(TAG_DE_GEOM_DEF)[0]
                
                feature_class.add_field(fld)
            
            if self.pg_drop_before:
                sql = "DROP TABLE IF EXISTS %s.%s CASCADE;\n" % (self.pg_schema, name) 
            sql += str(feature_class)
            return [name, sql, feature_class.list_fields()] 
        else:
            return None

    def get_gpkg_vector_layer(self, name):
        """
        Return a QgsVectorLayer by name
        """
        layer = None
        try:
            gpkg_layer_name = self.gpkg_path + "|layername=" + name
            vlayer = QgsVectorLayer(gpkg_layer_name, name, "ogr")
            if vlayer.isValid():
                layer = vlayer
        except Exception as e:
            print(e)
        return layer

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        self.xml_path = parameters["XMLPATH"]
        self.gpkg_path = parameters["GPKGPATH"]
        if not self.xml_path.lower().endswith(".xml"):
            feedback = QgsProcessingMultiStepFeedback(0, model_feedback)
            feedback.reportError("XML Workspace Definition is not an XML file!", True)
            return {}
        if not self.gpkg_path.lower().endswith(".gpkg"):
            feedback = QgsProcessingMultiStepFeedback(0, model_feedback)
            feedback.reportError("GeoPackage is not an GPKG file!", True)
            return {}    
        self.pg_conn_name = parameters["DBNAME"]
        self.pg_schema = parameters["SCHEMA"]
        self.pg_drop_before = parameters["DROPIFEXISTS"]
        dataset_list = self.getDatasets()
        feedback = QgsProcessingMultiStepFeedback(1+len(dataset_list), model_feedback)        
        step=0
        for dataset in dataset_list:
            step+=1
            definition = self.getDatasetDef(dataset)
            if definition is not None:
                try:
                    in_layer = self.get_gpkg_vector_layer(definition[0])
                    if in_layer is not None:
                        alg_params = {
                            'DATABASE': self.pg_conn_name,
                            'SQL': definition[1]
                        }
                        processing.run('qgis:postgisexecutesql', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
                        
                        # Esporta in PostgreSQL
                        alg_params = {
                            'CREATEINDEX': False,
                            'DATABASE': self.pg_conn_name,
                            'DROP_STRING_LENGTH': False,
                            'ENCODING': 'UTF-8',
                            'FORCE_SINGLEPART': False,
                            'GEOMETRY_COLUMN': 'geom',
                            'INPUT': self.get_gpkg_vector_layer(definition[0]),
                            'LOWERCASE_NAMES': True,
                            'OVERWRITE': True,
                            'PRIMARY_KEY': '',
                            'SCHEMA': self.pg_schema,
                            'TABLENAME': definition[0].lower() + '_tmp'
                        }
                        processing.run('qgis:importintopostgis', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
                        
                        #Copy from TMP to FINAL table
                        sql_copy = "INSERT INTO %s.%s(%s) SELECT %s FROM %s.%s_tmp" % (self.pg_schema, definition[0], definition[2], definition[2], self.pg_schema, definition[0]) + ";"
                        sql_drop = "DROP TABLE %s.%s_tmp" % (self.pg_schema, definition[0]) + ";"
                        alg_params = {
                            'DATABASE': self.pg_conn_name,
                            'SQL': sql_copy + sql_drop
                        }
                        processing.run('qgis:postgisexecutesql', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
                        
                        feedback.pushInfo("Feature Class: " + definition[0])
                except Exception as e:
                    feedback.reportError("Error importing domain " + definition[0] + ": " + str(e), False)
            feedback.setCurrentStep(step)
        results = {}
        outputs = {}
        return results

    def name(self):
        return 'KhrisXMLFeatureClassesImporterAlgorithm'

    def displayName(self):
        return 'XML Feature Classes Importer'

    def group(self):
        return 'krihs'

    def groupId(self):
        return 'krihs'

    def createInstance(self):
        return KhrisXMLFeatureClassesImporterAlgorithm()