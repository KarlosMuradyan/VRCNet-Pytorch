import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import vgg
from icecream import ic
from torchvision.models.resnet import resnet18

class UpBlock(nn.Module):
    def __init__(self, input_channels, output_channels, include_batch_norm=True):
        super(UpBlock, self).__init__()
        
        if include_batch_norm:
            self.up = nn.Sequential(
                nn.Conv2d(input_channels, output_channels, 
                    kernel_size=5, stride=1,
                    padding=2, bias=False),
                nn.BatchNorm2d(output_channels),
                nn.ReLU()
            )
        else:
            self.up = nn.Sequential(
                nn.Conv2d(input_channels, output_channels, 
                    kernel_size=5, stride=1,
                    padding=2, bias=True),
                nn.ReLU()
            )

    def forward(self, x):
        return self.up(x)

class VRCNet(nn.Module):
    def __init__(self, output_channels=1, freeze_layers=False):
        super(VRCNet, self).__init__()

        self.first_conv = nn.Conv2d(1, 3, kernel_size=5,
                stride=1, padding=2)
 
        #Defining ResNet
        resnet = resnet18(pretrained=True)
        self.resnet_layer0 = nn.Sequential(
            resnet.conv1,
            resnet.bn1,
            resnet.relu
        )

        self.resnet_maxpool1 = resnet.maxpool

        self.resnet_layer1 = resnet.layer1
        self.resnet_layer2 = resnet.layer2
        self.resnet_layer3 = resnet.layer3
        self.resnet_layer4 = resnet.layer4

        # Freeze layers
        if freeze_layers:
            self.resnet_layer1.require_grad = False
            self.resnet_layer2.require_grad = False
            self.resnet_layer3.require_grad = False
        del resnet

        #Defining VGG
        self.vgg = vgg.vgg16_bn(pretrained=True).features

        # Freezing layers
        if freeze_layers:
            for submod in self.vgg[:32]:
                for parameter in submod.parameters():
                    parameter.require_grad = False
        
        self.mid_conv = nn.Conv2d(1024, 1024, kernel_size=5,
                stride=1, padding=2)

        self.up4 = UpBlock(1792, 512)
        self.up3 = UpBlock(1152, 256)
        self.up2 = UpBlock(576, 128)
        self.up1 = UpBlock(320, 64)
        self.up0 = UpBlock(64, 32)

        self.last_conv = nn.Sequential(
                nn.Conv2d(32, 1,
                kernel_size = 5, stride=1,
                padding=2),
                nn.Sigmoid()
            )

    def forward(self, x):
        inp = self.first_conv(x)
        inp = nn.ReLU().forward(inp)

        #Passing through VGG
        d = inp
        necessary_shapes = []
        necessary_outputs = []
        for ii, sub_model in  enumerate(self.vgg):
            d = sub_model(d)
            if ii in {5, 12, 22, 32, 42}:
                # ic(d.shape)
                if ii in {12, 22, 32, 42}:
                    necessary_outputs.append(d)
                necessary_shapes.append(d.shape[-2:])

        #Passing through ResNet
        resnetl_0 = self.resnet_layer0(inp)
        resnetl_0_maxpool = self.resnet_maxpool1(resnetl_0)
        resnetl_1 = self.resnet_layer1(resnetl_0_maxpool)
        resnetl_2 = self.resnet_layer2(resnetl_1)
        resnetl_3 = self.resnet_layer3(resnetl_2)
        resnetl = self.resnet_layer4(resnetl_3)

        mid = torch.cat([resnetl[:,:,:d.shape[2], :d.shape[3]], d], dim=1)

        mid = self.mid_conv(mid)
        mid = nn.ReLU().forward(mid)

        up = F.interpolate(mid, size=(necessary_shapes[4]))
        up = torch.cat([up, necessary_outputs[3], resnetl_3[:,:,:up.shape[2], :up.shape[3]]], dim=1)
        up = self.up4(up)

        up = F.interpolate(up, size=(necessary_shapes[3]))
        up = torch.cat([up, necessary_outputs[2], resnetl_2[:,:,:up.shape[2], :up.shape[3]]], dim=1)
        up = self.up3(up)

        up = F.interpolate(up, size=(necessary_shapes[2]))
        up = torch.cat([up, necessary_outputs[1], resnetl_1[:,:,:up.shape[2], :up.shape[3]]], dim=1)
        up = self.up2(up)

        up = F.interpolate(up, size=(necessary_shapes[1]))
        up = torch.cat([up, necessary_outputs[0], resnetl_0[:,:,:up.shape[2], :up.shape[3]]], dim=1)
        up = self.up1(up)

        up = F.interpolate(up, size=(necessary_shapes[0]))
        up = self.up0(up)
        up = self.last_conv(up)

        return up

