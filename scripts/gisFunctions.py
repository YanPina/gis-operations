import warnings

import utm
import geopandas as gpd

from shapely.wkt import loads
from shapely.validation import make_valid

warnings.filterwarnings("ignore") #Remove UserWarning


class Shapefile:
        def __init__(self, file:str, dissolve:bool=False) -> None:
                self.file = file
                self.dissolve = dissolve

        
        def _open(self) -> gpd.GeoDataFrame:
                if not self.dissolve:
                        return self.__open_shapefile()

                else:
                        return self.__open_and_dissolve_shapefile()


        def __open_shapefile(self) -> gpd.GeoDataFrame:
                geodataframe = gpd.read_file(self.file)
                return MakeValidGeometries(geodataframe=geodataframe)._improve_geometry()


        def __open_and_dissolve_shapefile(self) -> gpd.GeoDataFrame:
                geodataframe = self.__open_shapefile()

                return Dissolve(geodataframe)._dissolve_geodataframe()


class ReprojectGeometries:

        def __init__(self, geodataframe: gpd.GeoDataFrame, to:str) -> None:
                self.to = to
                self.geodataframe = geodataframe


        def _reproject(self) -> gpd.GeoDataFrame:
                
                match self.to:
                        case 'utm':
                                return self.__reproject_to_utm()

                        case '4326':
                                return self.__reproject_to_4326()
                        

        def __reproject_to_utm(self) -> gpd.GeoDataFrame:

                for idx, row in self.geodataframe.iterrows():
                        c = row.geometry.centroid
                        utm_x, utm_y, band, zone = utm.from_latlon(c.y, c.x)

                        if c.y > 0:  # Northern zone
                                epsg = 32600 + band
                        else:
                                epsg = 32700 + band

                                try:
                                        self.geodataframe = self.geodataframe.to_crs(epsg=epsg)
                                except:
                                        self.geodataframe.crs = f"EPSG:{epsg}"
                
                return gpd.GeoDataFrame(self.geodataframe)


        def __reproject_to_4326(self) -> gpd.GeoDataFrame:
                try:
                        self.geodataframe = self.geodataframe.to_crs(epsg=4326)
                except:
                        self.geodataframe.crs = "EPSG:4326"


                return gpd.GeoDataFrame(self.geodataframe)



class Intersection:

        def __init__(self, geodataframe1: gpd.GeoDataFrame, geodataframe2: gpd.GeoDataFrame):
                self.geodataframe1 = MakeValidGeometries(geodataframe=geodataframe1)._improve_geometry()
                self.geodataframe2 = MakeValidGeometries(geodataframe=geodataframe2)._improve_geometry()
        

        def _intersection(self) -> gpd.GeoDataFrame:
                intersect = gpd.overlay(self.geodataframe1, self.geodataframe2, how='intersection')

                return MakeValidGeometries(geodataframe=intersect)._improve_geometry()



class Area:

        def __init__(self, geodataframe: gpd.GeoDataFrame, column_name:str = 'AREA_CALC') -> None:
                self.column_name = column_name
                self.geodataframe = ReprojectGeometries(geodataframe, to='utm')._reproject()


        def _calculate_area(self) -> gpd.GeoDataFrame:
                
                self.geodataframe[f'{self.column_name}'] = round(self.geodataframe['geometry'].area / 10000, 7)
                self.geodataframe = self.geodataframe.loc[self.geodataframe[f'{self.column_name}'] > 0.0000001]
                                
                return ReprojectGeometries(geodataframe=self.geodataframe, to='4326')._reproject()



class Dissolve:

        def __init__(self, geodataframe:gpd.GeoDataFrame, dissolve_atributes:list, calc_area:bool=False) -> None:      
                self.calc_area = calc_area
                self.dissolve_atributes = dissolve_atributes
                self.geodataframe = geodataframe


        def _dissolve_geodataframe(self) -> gpd.GeoDataFrame:
                try:
                        geodataframe_dissolve = self.geodataframe.dissolve(by=self.dissolve_atributes, as_index=False)
      
                except:
                        geodataframe_dissolve = MakeValidGeometries(geodataframe=self.geodataframe)._improve_geometry()
                        geodataframe_dissolve = geodataframe_dissolve.dissolve(by=self.dissolve_atributes, as_index=False)
                
                if geodataframe_dissolve.empty:
                        raise ValueError("GEOMETRIA IS EMPTY!!!")
                
                geodataframe_dissolve = MakeValidGeometries(geodataframe=geodataframe_dissolve)._improve_geometry()
                
                if self.calc_area:
                        geodataframe_dissolve = Area(geodataframe=geodataframe_dissolve)._calculate_area()

                return ReprojectGeometries(geodataframe=geodataframe_dissolve, to='4326')._reproject()


class ExplodeGeometries:

        def __init__(self, geodataframe: gpd.GeoDataFrame) -> None:
                self.geodataframe = MakeValidGeometries(geodataframe=geodataframe)._improve_geometry()
        

        def _explode(self) -> gpd.GeoDataFrame:
                return self.geodataframe.explode(index_parts=False, ignore_index=True)



class SpacialJoin:

        def __init__(self, geodataframe1: gpd.GeoDataFrame, geodataframe2: gpd.GeoDataFrame) -> None:
                self.geodataframe1 = MakeValidGeometries(geodataframe=geodataframe1)._improve_geometry()
                self.geodataframe1 = self.geodataframe1[['geometry']]

                self.geodataframe2 = MakeValidGeometries(geodataframe=geodataframe2)._improve_geometry()

        
        def _join_nearest(self) -> gpd.GeoDataFrame:
       
                sjoin = gpd.sjoin_nearest(
                        left_df=self.geodataframe1, 
                        right_df=self.geodataframe2, 
                        how="left", 
                        distance_col="distances"
                )
                
                return MakeValidGeometries(geodataframe=sjoin)._improve_geometry()


class MakeValidGeometries:

        def __init__(self, geodataframe:gpd.GeoDataFrame) -> None:
                self.geon_type_list:list = ['Polygon', 'MultiPolygon', 'GeometryCollection']
                
                
                self.geodataframe = gpd.GeoDataFrame(
                        geodataframe.loc[
                                (~geodataframe.is_empty) & 
                                (geodataframe['geometry'].geom_type.isin(self.geon_type_list))
                        ]
                )

        
        def _improve_geometry(self) -> gpd.GeoDataFrame:
                new_geodataframe = self.__improve_geometry_collection()
                
                return self.__make_valid(new_geodataframe)
        

        def __improve_geometry_collection(self) -> gpd.GeoDataFrame:
                # Repair broken geometries
                for index, row in self.geodataframe.iterrows(): # Looping over all polygons
                        if row['geometry'].geom_type == 'GeometryCollection':

                                new_geometry = ImproveGeometryCollections(
                                        row_geometry=row['geometry']
                                )._geometry_collection_to_multipolygon()

                                self.geodataframe.loc[[index],'geometry'] =  new_geometry # issue with Poly > Multipolygon

                return self.geodataframe


        def __make_valid(self, geodataframe:gpd.GeoDataFrame) -> gpd.GeoDataFrame:
                
                # Repair broken geometries
                for index, row in geodataframe.iterrows(): # Looping over all polygons

                        if not row['geometry'].is_valid:

                                fix = make_valid(row['geometry'])
                                try:
                                        geodataframe.loc[[index],'geometry'] =  fix # issue with Poly > Multipolygon
                                except ValueError:
                                        geodataframe.loc[[index],'geometry'] =  geodataframe.loc[[index], 'geometry'].buffer(0)

                geodataframe['geometry'] = geodataframe.buffer(0)

                return ReprojectGeometries(geodataframe=geodataframe, to='4326')._reproject()
    


class ImproveGeometryCollections:
        def __init__(self, row_geometry:gpd.GeoSeries) -> None:
                self.row_geometry = row_geometry
                
        
        def _geometry_collection_to_multipolygon(self, new_gdf:gpd.GeoDataFrame=gpd.GeoDataFrame()) -> gpd.GeoDataFrame:
                
                for geometry in self.row_geometry.geoms:
                        if geometry.geom_type != 'LineString':
                                new_gdf = new_gdf.append(self.__multipolygon_to_polygons(geometry))

                new_multipolygon = gpd.GeoDataFrame(new_gdf.dissolve())

                return self.__get_new_geometry(new_multipolygon['geometry'])


        def __multipolygon_to_polygons(self, row_multipolygon_geometry:gpd.GeoSeries) -> gpd.GeoDataFrame:
                d = {'geometry': [row_multipolygon_geometry]}
                gdf = gpd.GeoDataFrame(d, crs="EPSG:4326")

                return gpd.GeoDataFrame(gdf.explode())
        

        def __get_new_geometry(self, new_multipolygon:gpd.GeoSeries):
                geom_string=str(gpd.GeoSeries(new_multipolygon).geometry.values[0])
                return loads(geom_string).buffer(0)
        

class RemoveOverlay:
    
        def __init__(self, geodataframe: gpd.GeoDataFrame) -> None:
                self.geodataframe = geodataframe
                self.geodataframe = self.geodataframe.reset_index(drop=True)
                self.geodataframe['REF'] = self.geodataframe.index

                self.processed_list:list = []

        def _improve_geometries(self) -> gpd.GeoDataFrame:
                geometry = self.geodataframe
                try:
                        return self.__remove_geometry_overlays(geodataframe=geometry)
                except:
                        new_farm_geometry = MakeValidGeometries(geodataframe=geometry)._improve_geometry()
                        return self.__remove_geometry_overlays(geodataframe=new_farm_geometry)


        
        def __remove_geometry_overlays(self, geodataframe:gpd.GeoDataFrame) -> gpd.GeoDataFrame:
                
                for index1, row1 in geodataframe.iterrows():
                        for index2, row2 in geodataframe.iterrows():
                                
                                if self.__is_an_overlap(geodataframe=geodataframe, row1=row1, row2=row2):
                                        
                                        geom_string=str(gpd.GeoSeries([row2['geometry'].difference(row1['geometry'])]).geometry.values[0])
                                        geom = loads(geom_string).buffer(0)

                                        geodataframe.loc[geodataframe['REF'] == geodataframe.loc[geodataframe['REF'] == row2['REF']]['REF'].values[0], 'geometry'] = gpd.GeoSeries([geom]).values                

                        self.processed_list.append(row1['REF'])
                        
                return ReprojectGeometries(geodataframe=geodataframe, to='4326')._reproject()
                        
        
        def __is_diffent_row(self, row1:gpd.GeoSeries, row2:gpd.GeoSeries) -> bool:
                if row1['REF'] != row2['REF']:
                        return True
                else:
                        return False
                
        
        def __not_in_processed(self, row1:gpd.GeoSeries, row2:gpd.GeoSeries) -> bool:
                if (row1['REF'] not in self.processed_list) & (row2['REF'] not in self.processed_list):
                        return True
                else:
                        return False
        
        
        def __is_an_overlap(self, geodataframe:gpd.GeoDataFrame, row1:gpd.GeoSeries, row2:gpd.GeoSeries) -> bool:
                is_overlap = CheckOverlap(geodataframe=geodataframe, row1=row1, row2=row2)._is_overlay()
                is_different = self.__is_diffent_row(row1=row1, row2=row2)
                is_not_processed = self.__not_in_processed(row1=row1, row2=row2)

                if is_overlap & is_different & is_not_processed:
                        return True
                else:
                        return False


class CheckOverlap:
        def __init__(self, geodataframe:gpd.GeoDataFrame, row1:gpd.GeoSeries, row2:gpd.GeoSeries) -> None:
                self.row1 = row1
                self.row2 = row2
                self.geodataframe = geodataframe
        

        def _is_overlay(self) -> bool:
                try:
                        if self.__is_overlap() | self.__is_intersect():
                                return True
                        else:
                                return False
                except:
                        return False


        def __is_overlap(self) -> bool:
                gdf_row1 = self.__create_fragment_geodataframe(self.row1['REF'])
                gdf_row2 = self.__create_fragment_geodataframe(self.row2['REF'])

                overlap = gdf_row1.overlaps(gdf_row2, align=False)
                
                if overlap.bool():
                        return True
                else:
                        return False
                

        def __is_intersect(self) -> bool:
                if self.row1['geometry'].intersection(self.row2['geometry']):
                        return True
                else:
                        return False

        
        def __create_fragment_geodataframe(self, ref_index:str) -> gpd.GeoDataFrame:
                geodataframe_row = gpd.GeoDataFrame(self.geodataframe.loc[self.geodataframe['REF'] == ref_index])
                
                return geodataframe_row[['geometry', 'REF']]
