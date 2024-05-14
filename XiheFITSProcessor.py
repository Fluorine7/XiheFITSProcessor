import os
import tkinter as tk
from tkinter import filedialog, scrolledtext, Checkbutton, IntVar
from astropy.io import fits
import numpy as np
import struct

#本代码由@正七价的氟离子BA7LFN 总结并发布，用于处理羲和号获取的RSM一级数据

# 根据全局最小和最大值缩放图像数据
def scale_image_data(data, global_min, global_max):
    data_scaled = (data - global_min) / (global_max - global_min) * 65535
    return data_scaled.astype(np.uint16)

# 将FITS文件写入SER文件
def write_ser(file_paths, output_dir, image_width, image_height, num_frames, base_filename, color_id=0, little_endian=True):
    header_format = '<14s I I I I I I I 40s 40s 40s Q Q'
    observer_name = b"Observer Name" + b'\x00' * (40 - len("Observer Name"))
    camera_model = b"Camera Model" + b'\x00' * (40 - len("Camera Model"))
    telescope_name = b"Telescope Name" + b'\x00' * (40 - len("Telescope Name"))
    
    output_filename = f"{os.path.splitext(base_filename)[0]}.ser"
    output_path = os.path.join(output_dir, output_filename)
    
    header = struct.pack(header_format,
                         b"LUCAM-RECORDER",
                         0,
                         color_id,
                         0 if little_endian else 1,
                         image_width,
                         image_height,
                         16,
                         num_frames,
                         observer_name,
                         camera_model,
                         telescope_name,
                         0,
                         0)

    with open(output_path, 'wb') as ser_file:
        ser_file.write(header)
        for path in file_paths:
            with fits.open(path) as hdul:
                image_data_index = 1 if len(hdul) > 1 else 0
                image_data = hdul[image_data_index].data.astype(np.uint16)
                ser_file.write(image_data.tobytes())
        print(f"SER file saved as {output_filename}")

# 保存FITS文件并处理SER文件
def split_and_save_fits(file_paths, output_dir, console, ser_option, delete_fits_option):
    for file_path in file_paths:
        with fits.open(file_path) as hdul:
            data = hdul[1].data
            header = hdul[1].header

        base_filename = os.path.basename(file_path)
        scan_dir_name = f"Scan_{base_filename[:-5]}"
        scan_dir_path = os.path.join(output_dir, scan_dir_name)
        os.makedirs(scan_dir_path, exist_ok=True)

        global_min = np.min(data)
        global_max = np.max(data)

        fits_files = []
        for i in range(data.shape[1]):
            slice_data = data[:, i, :]
            slice_data_scaled = scale_image_data(slice_data, global_min, global_max)
            new_filename = f"{base_filename[:-5]}_{i+1:04d}.fits"
            full_path = os.path.join(scan_dir_path, new_filename)
            fits.writeto(full_path, slice_data_scaled, header, overwrite=True)
            console.insert(tk.END, f"Saved slice {i+1} as {new_filename}\n")
            console.see(tk.END)
            fits_files.append(full_path)

        if ser_option.get():
            write_ser(fits_files, scan_dir_path, data.shape[2], data.shape[0], len(fits_files), base_filename, 0, 1)
            console.insert(tk.END, "SER file creation completed.\n")
            console.see(tk.END)

            if delete_fits_option.get():
                for path in fits_files:
                    os.remove(path)
                console.insert(tk.END, "All FITS files have been deleted.\n")
                console.see(tk.END)

# 用户选择文件
def select_file(console, ser_option, delete_fits_option):
    file_paths = filedialog.askopenfilenames(filetypes=[("FITS files", "*.fits"), ("All files", "*.*")])  # Changed to askopenfilenames
    if file_paths:
        output_dir = os.path.dirname(file_paths[0])
        split_and_save_fits(file_paths, output_dir, console, ser_option, delete_fits_option)

# 初始化GUI
root = tk.Tk()
root.title("Xihe FITS Processor")
root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(0, weight=1)

select_button = tk.Button(root, text="Select Fits Files", command=lambda: select_file(console, ser_option, delete_fits_option))
select_button.grid(row=0, column=0, padx=10, pady=2, sticky='w')

ser_option = IntVar()
ser_check = Checkbutton(root, text=" Generate SER videos", variable=ser_option)
ser_check.grid(row=1, column=0, padx=10, pady=2, sticky='w')

delete_fits_option = IntVar()
delete_fits_check = Checkbutton(root, text=" Delete new FITSs after generating SER videos", variable=delete_fits_option)
delete_fits_check.grid(row=2, column=0, padx=10, pady=2, sticky='w')

# 添加一个空行
empty_label1 = tk.Label(root, text="")
empty_label1.grid(row=3, column=0, sticky='w')

console = scrolledtext.ScrolledText(root, height=10, width=65)
console.grid(row=0, column=1, rowspan=5, padx=10, pady=2, sticky='nsew')

root.mainloop()
