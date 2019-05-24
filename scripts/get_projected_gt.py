#!/usr/bin/python

import sys, os, pdb
import numpy as np
import cv2
import argparse
from distort import DistortMap
from helper import get_cropped_uv_rotated, is_out_of_bound, is_out_of_bound_rotated
from label2color import  background, label_to_color
from pcl import pcl_visualization
import pcl

def gt_viewer(lidar_final, labels_final):
    lidar = np.transpose(lidar_final).astype(np.float32)
    cloud = pcl.PointCloud_PointXYZRGB()
    for i in range(len(labels_final) ):
        # set Point Plane
        if labels_final[i] in label_to_color:
            color = label_to_color[labels_final[i]]
        else:
            color = label_to_color[0]
        
        lidar[i][3] = color[2] << 16 | color[1] << 8 | color[0]
    cloud.from_array(lidar)
    visual = pcl_visualization.CloudViewing()
    visual.ShowColorCloud(cloud)

    v = True
    while v:
        v=not(visual.WasStopped())

def gt_projection(lidar, lidar_distribution,
                  rgb_img, gt_img, cam2lidar, intrinsic, distort_map, output_file):

    num_classes = lidar_distribution.shape[0]
    
    # project lidar points into camera coordinates
    T_c2l = cam2lidar[:3, :]

    lidar_in_cam = np.matmul(intrinsic, T_c2l )
    projected_lidar_2d = np.matmul( lidar_in_cam, lidar)
    projected_lidar_2d[0, :] = projected_lidar_2d[0, :] / projected_lidar_2d[2, :]
    projected_lidar_2d[1, :] = projected_lidar_2d[1, :] / projected_lidar_2d[2, :]

    # filter the points on the image
    idx_infront = projected_lidar_2d[2, :]>0
    print("idx_front sum is " + str(np.sum(idx_infront)))
    filtered_distribution = lidar_distribution[:, idx_infront]
    points_on_img = projected_lidar_2d[:, idx_infront]
    lidar_on_img = lidar[:, idx_infront]

                
    # distort the lidar points based on the distortion map file
    projected_lidar_2d, remaining_ind = distort_map.distort(points_on_img)
    lidar_on_img = lidar_on_img[:, remaining_ind]
    filtered_distribution = filtered_distribution[:, remaining_ind]
    print(projected_lidar_2d.shape, lidar_on_img.shape, filtered_distribution.shape)
        
    projected_points = []
    projected_index  = []  # just for visualization
    labels = []
    original_rgb = []
    class_distribution = []
    gt_label_file = open(output_file, 'w')
    for col in range(projected_lidar_2d.shape[1]):
        u, v, _ = projected_lidar_2d[:, col]
        u ,v = get_cropped_uv_rotated(u, v, rgb_img.shape[1] * 1.0 / 1200 )
        if is_out_of_bound(u, v, rgb_img.shape[1], rgb_img.shape[0]):
            continue
        projected_points.append(lidar_on_img[:, col])

        if gt_img[v, u] < num_classes :
            label = gt_img[int(v), int(u)]
        else:
            label = 0
        labels.append(label)

        # write gt results to the file
        gt_label_file.write("{} {} {} ".format(lidar_on_img[0, col], lidar_on_img[1, col], lidar_on_img[2, col]))
        for i in range(num_classes):
            gt_label_file.write("{} ".format(filtered_distribution[i, col]))
        gt_label_file.write(str(label))
        gt_label_file.write("\n")
        if abs(lidar_on_img[2, col]) == 0.215:
            print(lidar_on_img[:, col])
            print(filtered_distribution[:, col])

        
	original_rgb.append(rgb_img[int(v), int(u), :])
        projected_index.append(col)
    gt_label_file.close()

    lidars_left = lidar_on_img[:, projected_index]
    distribution_left = filtered_distribution[:, projected_index]
    #######################################################################
    # for debug use: visualize the projection on the original rgb image
    #######################################################################
    img_to_vis = np.zeros((gt_img.shape[0], gt_img.shape[1], 3))
    img_to_vis[:,:,0] = gt_img
    img_to_vis[:,:,1] = gt_img
    img_to_vis[:,:,2] = gt_img
    
    for j in range(len(projected_index)):
        col = projected_index[j]
        u = int(round(projected_lidar_2d[0, col] , 0))
        v = int(round(projected_lidar_2d[1, col] , 0))
        u ,v = get_cropped_uv_rotated(u, v, rgb_img.shape[1] * 1.0 / 1200 )
        if labels[j] in label_to_color:
            color = label_to_color[labels[j]]
        else:
            color = label_to_color[0]

        cv2.circle(img_to_vis, (u, v),2, color)
    cv2.imshow("gt projection", img_to_vis)
    cv2.waitKey(1000)
    ########################################################################
    return lidars_left, labels, distribution_left


def read_input_pc_with_distribution(file_name):
    lidar = []
    lidar_distribution = []
    with open(file_name) as f:
        for line in f:
            point = line.split()
            point_np = np.array([float(item) for item in point])

            lidar.append(np.array([point_np[0],point_np[1],point_np[2], 1]))
            
            lidar_distribution.append(point_np[3:])
            if abs(point_np[2]) == 0.215:
                print(point)
                

    lidar = np.transpose(np.array(lidar))
    lidar_distribution = np.transpose(np.array(lidar_distribution))
    print("Finish reading data... lidar shape is {}, lidar_distribution shape is {}".format(lidar.shape, lidar_distribution.shape))
    return lidar, lidar_distribution

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--input_pointcloud',  type=str, nargs=1)
    parser.add_argument('--rgb_img', type=str, nargs=1)
    parser.add_argument('--gt_img', type=str, nargs=1)
    parser.add_argument('--cam2lidar_projection', type=str, nargs=1)
    parser.add_argument('--cam_intrinsic', type=str, nargs=1)
    parser.add_argument('--distortion_map', type=str, nargs=1)
    parser.add_argument('--output_pointcloud', type=str, nargs=1)

    args = parser.parse_args()
    print(args.input_pointcloud[0])
    lidar, lidar_distribution = read_input_pc_with_distribution(args.input_pointcloud[0])
    T_cam2lidar = np.load(args.cam2lidar_projection[0])
    intrinsic = np.load(args.cam_intrinsic[0])
    distort = DistortMap(args.distortion_map[0])

    rgb = cv2.imread(args.rgb_img[0])
    gt = cv2.imread(args.gt_img[0])[:,:,0]

    lidars_left, labels, distribution_left = gt_projection(lidar,
                                                           lidar_distribution,
                                                           rgb,
                                                           gt,
                                                           T_cam2lidar,
                                                           intrinsic,
                                                           distort,
                                                           args.output_pointcloud[0])
    pdb.set_trace()
    gt_viewer(lidars_left, labels)

    