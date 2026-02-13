import pygame

pygame.mixer.init()
# 直接指向系统文件
pygame.mixer.Sound(r"C:\Windows\Media\Windows Notify.wav").play()