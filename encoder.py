'''Encode target locations and class labels.'''
import math
import torch

from utils import meshgrid, box_iou, change_box_order


class DataEncoder:
    def __init__(self):
        self.anchor_areas = [32*32., 64*64., 128*128., 256*256., 512*512.]  # p3 -> p7
        self.aspect_ratios = [1/2., 1/1., 2/1.]
        self.scale_ratios = [1., pow(2,1/3.), pow(2,2/3.)]
        self.anchor_wh = self._get_anchor_wh()

    def _get_anchor_wh(self):
        '''Compute anchor width and height for each feature map.

        Returns:
          anchor_wh: (tensor) anchor wh, sized [#fm, #anchors_per_cell, 2].
        '''
        anchor_wh = []
        for s in self.anchor_areas:
            for ar in self.aspect_ratios:  # w/h = ar
                h = math.sqrt(s/ar)
                w = ar * h
                for sr in self.scale_ratios:  # scale
                    anchor_h = h*sr
                    anchor_w = w*sr
                    anchor_wh.append([anchor_w, anchor_h])
        num_fms = len(self.anchor_areas)
        return torch.Tensor(anchor_wh).view(num_fms, -1, 2)

    def _get_anchor_boxes(self, input_size):
        '''Compute anchor boxes for each feature map.

        Args:
          input_size: (int) model input size.

        Returns:
          boxes: (list) anchor boxes for each feature map. Each of size [#total_anchors,4],
                        where #total_anchors = fmh * fmw * #anchors_per_cell
        '''
        num_fms = len(self.anchor_areas)
        fm_sizes = [int(input_size/pow(2.,i+3)+0.5) for i in range(num_fms)]  # p3 -> p7 feature map sizes
        # TODO: make sure computed fm_sizes is the same as feature_map sizes

        boxes = []
        for i in range(num_fms):
            fm_size = fm_sizes[i]
            grid_size = input_size//fm_size
            xy = meshgrid(fm_size, swap_dims=True) + 0.5  # [fm_size*fm_size,2]
            xy = (xy*grid_size).view(fm_size,fm_size,1,2).expand(fm_size,fm_size,9,2)
            wh = self.anchor_wh[i].view(1,1,9,2).expand(fm_size,fm_size,9,2)
            box = torch.cat([xy,wh], 3)  # [x,y,w,h]
            boxes.append(box.view(-1,4))
        return torch.cat(boxes, 0)

    def encode(self, boxes, labels, input_size):
        '''Encode target bounding boxes and class labels.

        Args:
          boxes: (tensor) bounding boxes of (xmin,ymin,xmax,ymax) in range [0,1], sized [#obj, 4].
          labels: (tensor) object class labels, sized [#obj,].
          input_size: (int) model input size.

        Returns:
          loc_targets: (tensor) encoded bounding boxes, sized [#total_anchors,4].
          cls_targets: (tensor) encoded class labels, sized [#total_anchors].
        '''
        anchor_boxes = self._get_anchor_boxes(input_size)
        boxes = change_box_order(boxes, 'xyxy2xywh')
        boxes = boxes * input_size  # scale to range [0,input_size]

        ious = box_iou(anchor_boxes, boxes, order='xywh')
        max_ious, max_ids = ious.max(1)
        boxes = boxes[max_ids]

        loc_xy = (boxes[:,:2]-anchor_boxes[:,:2]) / anchor_boxes[:,2:]
        loc_wh = torch.log(boxes[:,2:]/anchor_boxes[:,2:])
        loc_targets = torch.cat([loc_xy,loc_wh], 1)
        cls_targets = 1 + labels[max_ids]

        cls_targets[max_ious<0.4] = 0
        ignore = (max_ious>0.4) & (max_ious<0.5)  # ignore ious between [0.4,0.5]
        cls_targets[ignore] = -1  # for now just mark ignored to -1
        return loc_targets, cls_targets


def test():
    in_size = 600
    c3_size = 75
    grid_size = in_size/c3_size
    cx = grid_size/2.
    cy = grid_size/2.
    w = 32
    h = 32
    boxes = torch.Tensor([[cx-w/2.,cy-w/2.,cx+w/2.,cy+w/2.]])
    labels = torch.LongTensor([1])
    boxes /= torch.Tensor([in_size,in_size,in_size,in_size]).expand_as(boxes)
    encoder = DataEncoder()
    loc_targets, cls_targets = encoder.encode(boxes, labels, input_size=in_size)

def test2():
    line = '335 500 139 200 207 301 18'
    # line = '354 480 87 97 258 427 12 133 72 245 284 14'
    sp = line.strip().split()
    w = float(sp[0])
    h = float(sp[1])
    N = (len(sp)-2)//5
    boxes = []
    labels = []
    for i in range(N):
        boxes.append([float(x) for x in [sp[5*i+2],sp[5*i+3],sp[5*i+4],sp[5*i+5]]])
        labels.append(int(sp[5*i+6]))

    boxes = torch.Tensor(boxes)
    labels = torch.LongTensor(labels)
    boxes /= torch.Tensor([w,h,w,h]).expand_as(boxes)

    encoder = DataEncoder()
    loc_targets, cls_targets = encoder.encode(boxes, labels, input_size=600)

# test()
