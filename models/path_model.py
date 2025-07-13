import copy

class PathModel:
    def __init__(self):
        self.__points = []
    
    def get_points(self):
        return copy.deepcopy(self.__points)
    
    def get_point(self, index):
        return copy.deepcopy(self.__points[index])

    def set_points(self, new_points):
        self.__points = copy.deepcopy(new_points)

    def add_point(self, x, y, point_type='translation'):
        self.__points.append({'x' : x, 'y' : y, 'type' : point_type, 'params' : {} })
    
    def update_point(self, index, key, value):
        if 0 <= index < len(self.__points):
            if key in ['x', 'y', 'type']:
                self.__points[index][key] = value
            else:
                self.__points[index]['params'][key] = value

    def reorder_points(self, new_order):
        if len(new_order) != len(self.__points):
            raise ValueError("New order must match points length")
        self.__points = [self.__points[i] for i in new_order]