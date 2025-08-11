import os
import tkinter as tk
from tkinter import filedialog, scrolledtext, Checkbutton, IntVar, Label, Entry, Button, Frame
import numpy as np
import struct
from astropy.io import fits
from datetime import datetime, timezone, timedelta
import multiprocessing
import traceback

# 本代码由@正七价的氟离子BA7LFN 原始创建，并由ChatGPT 4与Manus AI进行修改和优化
# V2.0：
# 1. 增加多核处理逻辑。
# 2. 添加SER文件的Timestamps。
# 3. 确保每个任务完成后都能被正确、独立地处理，并实时更新UI进度。
# 4. 增加双语切换。

# --- 语言翻译字典 (保持不变) ---
LANG_STRINGS = {
    'window_title': {'en': "Xihe FITS to SER Converter (v2.0 By Fluorine Zhu)", 'zh': "羲和FITS转SER转换器 (v2.0 By 正七价的氟离子)"},
    'processing_title': {'en': "Processing... ({done}/{total})", 'zh': "处理中... ({done}/{total})"},
    'select_input_button': {'en': "Select Input FITS", 'zh': "选择输入FITS"},
    'select_output_button': {'en': "Select Output Dir", 'zh': "选择输出目录"},
    'files_selected': {'en': "{count} file(s) selected", 'zh': "已选择 {count} 个文件"},
    'option_generate_ser': {'en': "Generate SER videos", 'zh': "生成SER视频"},
    'option_delete_fits': {'en': "Delete new FITSs after generating SER videos", 'zh': "生成SER后删除临时FITS文件"},
    'start_button': {'en': "Start Processing", 'zh': "开始处理"},
    'log_label': {'en': "Log:", 'zh': "日志："},
    'switch_lang_button': {'en': "切换中文", 'zh': "Switch to English"},
    'log_error_no_selection': {'en': "Error: Input files or output directory not selected.", 'zh': "错误：未选择输入文件或输出目录。"},
    'log_error_in_progress': {'en': "Processing is already in progress.", 'zh': "处理已在进行中。"},
    'log_start_parallel': {'en': "Starting parallel processing for {count} files...", 'zh': "开始并行处理 {count} 个文件..."},
    'log_cpu_cores': {'en': "Using up to {count} CPU cores.", 'zh': "最多使用 {count} 个CPU核心。"},
    'log_processing_file': {'en': "--- Processing {filename} ---", 'zh': "--- 正在处理 {filename} ---"},
    'log_applying_stretch': {'en': "[{filename}] Applying expanded linear stretch...", 'zh': "[{filename}] 正在应用扩展线性拉伸..."},
    'log_slicing_fits': {'en': "[{filename}] Slicing and saving temporary FITS files...", 'zh': "[{filename}] 正在切片并保存临时FITS文件..."},
    'log_saved_fits': {'en': "[{filename}] Saved {count} temporary FITS files.", 'zh': "[{filename}] 已保存 {count} 个临时FITS文件。"},
    'log_generating_ser': {'en': "[{filename}] Generating SER video...", 'zh': "[{filename}] 正在生成SER视频..."},
    'log_ser_completed': {'en': "[{filename}] SER file generation completed.", 'zh': "[{filename}] SER文件生成完毕。"},
    'log_deleting_fits': {'en': "[{filename}] Deleting temporary FITS files...", 'zh': "[{filename}] 正在删除临时FITS文件..."},
    'log_fits_deleted': {'en': "[{filename}] All temporary FITS files have been deleted.", 'zh': "[{filename}] 所有临时FITS文件均已删除。"},
    'log_error_processing': {'en': "!!! ERROR processing {filename} !!!\n{error}", 'zh': "!!! 处理 {filename} 时发生错误 !!!\n{error}"},
    'log_batch_complete': {'en': "\n--- BATCH PROCESSING COMPLETE ---", 'zh': "\n--- 批量处理完成 ---"},
    'log_total_files': {'en': "Total files: {count}", 'zh': "文件总数：{count}"},
    'log_successful': {'en': "Successful: {count}", 'zh': "成功：{count}"},
    'log_failed': {'en': "Failed: {count}", 'zh': "失败：{count}"},
    'log_summary_line': {'en': "---------------------------------", 'zh': "---------------------------------"},
}

def scale_image_expanded_linear(data, base_black_perc=1.0, base_white_perc=99.9, expansion_factor=0.03):
    base_black = np.percentile(data, base_black_perc)
    base_white = np.percentile(data, base_white_perc)
    if base_white <= base_black: base_white = base_black + 1e-6
    base_range = base_white - base_black
    final_black = base_black - base_range * expansion_factor
    final_white = base_white + base_range * expansion_factor
    clipped_data = np.clip(data, final_black, final_white)
    scaled_data = (clipped_data - final_black) / (final_white - final_black) * 65535.0
    return scaled_data.astype(np.uint16)

def to_ser_timestamp(dt_obj):
    if not dt_obj or not isinstance(dt_obj, datetime): return 0
    ser_epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    time_difference = dt_obj - ser_epoch
    return int(time_difference.total_seconds() * 10_000_000)

def write_ser_with_correct_timestamps(file_paths, output_path, image_width, image_height, start_time, end_time):
    num_frames = len(file_paths)
    header_format = '<14s I I I I I I I 40s 40s 40s Q Q'
    observer_name, camera_model, telescope_name = b"Observer Name".ljust(40, b'\x00'), b"CHASE/HIS".ljust(40, b'\x00'), b"Xihe".ljust(40, b'\x00')
    header_timestamp = to_ser_timestamp(start_time)
    with open(output_path, 'wb') as ser_file:
        header = struct.pack(header_format, b"LUCAM-RECORDER", 0, 0, 0, image_width, image_height, 16, num_frames, observer_name, camera_model, telescope_name, header_timestamp, header_timestamp)
        ser_file.write(header)
        for path in file_paths:
            with fits.open(path) as hdul:
                ser_file.write(hdul[0].data.astype(np.uint16).tobytes())
        if start_time and end_time and num_frames > 1:
            total_duration = (end_time - start_time).total_seconds()
            time_step_seconds = total_duration / (num_frames - 1) if num_frames > 1 else 0
            for i in range(num_frames):
                frame_time = start_time + timedelta(seconds=(i * time_step_seconds))
                ser_file.write(struct.pack('<Q', to_ser_timestamp(frame_time)))

def process_single_file_task(args):
    file_path, output_dir, ser_option, delete_fits_option, log_queue = args
    base_filename = os.path.basename(file_path)
    
    def _log(key, **kwargs):
        log_queue.put({'lang_key': key, 'lang_args': kwargs})

    _log('log_processing_file', filename=base_filename)
    try:
        with fits.open(file_path) as hdul:
            data, header = hdul[1].data, hdul[1].header
            start_time = datetime.fromisoformat(header['STR_TIME']).replace(tzinfo=timezone.utc)
            end_time = datetime.fromisoformat(header['END_TIME']).replace(tzinfo=timezone.utc)
        
        scan_dir_name = f"Scan_{os.path.splitext(base_filename)[0]}"
        scan_dir_path = os.path.join(output_dir, scan_dir_name)
        os.makedirs(scan_dir_path, exist_ok=True)
        
        _log('log_applying_stretch', filename=base_filename)
        stretched_data = scale_image_expanded_linear(data)
        
        temp_fits_files = []
        _log('log_slicing_fits', filename=base_filename)
        image_height, num_frames, image_width = stretched_data.shape
        for i in range(num_frames):
            full_path = os.path.join(scan_dir_path, f"{os.path.splitext(base_filename)[0]}_{i+1:04d}.fits")
            fits.writeto(full_path, stretched_data[:, i, :], header, overwrite=True)
            temp_fits_files.append(full_path)
        _log('log_saved_fits', filename=base_filename, count=len(temp_fits_files))

        if ser_option:
            ser_output_path = os.path.join(scan_dir_path, f"{os.path.splitext(base_filename)[0]}.ser")
            _log('log_generating_ser', filename=base_filename)
            write_ser_with_correct_timestamps(temp_fits_files, ser_output_path, image_width, image_height, start_time, end_time)
            _log('log_ser_completed', filename=base_filename)
            if delete_fits_option:
                _log('log_deleting_fits', filename=base_filename)
                for path in temp_fits_files: os.remove(path)
                _log('log_fits_deleted', filename=base_filename)
        return (True, base_filename)
    except Exception:
        error_info = traceback.format_exc()
        _log('log_error_processing', filename=base_filename, error=error_info)
        return (False, base_filename)

class Application(Frame):
    def __init__(self, master=None):
        super().__init__(master, padx=10, pady=10)
        self.master = master
        self.pack(fill=tk.BOTH, expand=True)
        self.lang = 'en'
        self.input_paths = []
        self.processing = False
        self.create_widgets()
        self.update_ui_language()

    def get_string(self, key, **kwargs):
        template = LANG_STRINGS.get(key, {}).get(self.lang, f"_{key}_")
        return template.format(**kwargs)

    def create_widgets(self):
        top_frame = Frame(self)
        top_frame.pack(fill=tk.X, pady=(0, 5))
        self.lang_button = Button(top_frame, text="", command=self.toggle_language)
        self.lang_button.pack(side=tk.RIGHT)

        io_frame = Frame(self)
        io_frame.pack(fill=tk.X, pady=5)
        self.select_input_button = Button(io_frame, text="", command=self.select_input_files)
        self.select_input_button.pack(side=tk.LEFT, padx=(0, 5))
        self.input_entry = Entry(io_frame, state='readonly', width=50)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        io_frame2 = Frame(self)
        io_frame2.pack(fill=tk.X, pady=5)
        self.select_output_button = Button(io_frame2, text="", command=self.select_output_dir)
        self.select_output_button.pack(side=tk.LEFT, padx=(0, 5))
        self.output_entry = Entry(io_frame2, state='readonly', width=50)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        options_frame = Frame(self)
        options_frame.pack(fill=tk.X, pady=10)
        self.ser_option = IntVar(value=1)
        self.ser_check = Checkbutton(options_frame, text="", variable=self.ser_option)
        self.ser_check.pack(anchor='w')
        self.delete_fits_option = IntVar(value=1)
        self.delete_check = Checkbutton(options_frame, text="", variable=self.delete_fits_option)
        self.delete_check.pack(anchor='w')

        self.process_button = Button(self, text="", command=self.start_processing_logic)
        self.process_button.pack(pady=10)

        log_frame = Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_label = Label(log_frame, text="")
        self.log_label.pack(anchor='w')
        self.console = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.console.pack(fill=tk.BOTH, expand=True)

    def toggle_language(self):
        self.lang = 'zh' if self.lang == 'en' else 'en'
        self.update_ui_language()

    def update_ui_language(self):
        self.master.title(self.get_string('window_title'))
        self.lang_button.config(text=self.get_string('switch_lang_button'))
        self.select_input_button.config(text=self.get_string('select_input_button'))
        self.select_output_button.config(text=self.get_string('select_output_button'))
        self.ser_check.config(text=self.get_string('option_generate_ser'))
        self.delete_check.config(text=self.get_string('option_delete_fits'))
        self.process_button.config(text=self.get_string('start_button'))
        self.log_label.config(text=self.get_string('log_label'))

    def select_input_files(self):
        paths = filedialog.askopenfilenames(title="Select Input FITS Files", filetypes=[("FITS files", "*.fits")])
        if paths:
            self.input_paths = paths
            self.input_entry.config(state='normal')
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, self.get_string('files_selected', count=len(paths)))
            self.input_entry.config(state='readonly')
            if not self.output_entry.get():
                self.output_entry.config(state='normal')
                self.output_entry.delete(0, tk.END)
                self.output_entry.insert(0, os.path.dirname(paths[0]))
                self.output_entry.config(state='readonly')

    def select_output_dir(self):
        initial_dir = os.path.dirname(self.input_paths[0]) if self.input_paths else "/"
        path = filedialog.askdirectory(title="Select Output Directory", initialdir=initial_dir)
        if path:
            self.output_entry.config(state='normal')
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)
            self.output_entry.config(state='readonly')

    def log(self, key, **kwargs):
        message = self.get_string(key, **kwargs)
        self.console.insert(tk.END, message + '\n')
        self.console.see(tk.END)

    def check_log_queue(self):
        while not self.log_queue.empty():
            msg_data = self.log_queue.get()
            self.log(msg_data['lang_key'], **msg_data['lang_args'])
        if self.processing:
            self.master.after(100, self.check_log_queue)

    def start_processing_logic(self):
        if not self.input_paths or not self.output_entry.get():
            self.log('log_error_no_selection')
            return
        if self.processing:
            self.log('log_error_in_progress')
            return

        self.processing = True
        self.process_button.config(state='disabled')
        self.console.delete('1.0', tk.END)
        
        self.total_tasks = len(self.input_paths)
        self.successful_tasks = 0
        self.failed_tasks = 0
        
        self.master.title(self.get_string('processing_title', done=0, total=self.total_tasks))
        self.log('log_start_parallel', count=self.total_tasks)
        self.log('log_cpu_cores', count=multiprocessing.cpu_count())

        manager = multiprocessing.Manager()
        self.log_queue = manager.Queue()
        self.master.after(100, self.check_log_queue)

        # **核心修正**: 传递当前语言给子进程
        tasks = [(path, self.output_entry.get(), self.ser_option.get(), self.delete_fits_option.get(), self.log_queue) for path in self.input_paths]

        self.pool = multiprocessing.Pool()
        self.result_iterator = self.pool.imap_unordered(process_single_file_task, tasks)
        
        self.master.after(100, self.check_next_result)

    def check_next_result(self):
        """正确地、非阻塞地从迭代器中获取下一个结果"""
        try:
            # 使用一个极小的超时来检查是否有结果，避免阻塞GUI
            result = self.result_iterator.next(timeout=0.01)
            success, filename = result
            if success:
                self.successful_tasks += 1
            else:
                self.failed_tasks += 1
            
            done_count = self.successful_tasks + self.failed_tasks
            self.master.title(self.get_string('processing_title', done=done_count, total=self.total_tasks))
            
            # 快速安排下一次检查
            self.master.after(10, self.check_next_result)
        
        except StopIteration:
            # 迭代器已耗尽，所有任务完成
            self.on_processing_done()
        
        except multiprocessing.TimeoutError:
            # 本次检查没有结果，稍后重试
            self.master.after(100, self.check_next_result)

    def on_processing_done(self):
        """所有任务完成后调用的清理函数"""
        self.processing = False
        self.process_button.config(state='normal')
        self.pool.close()
        self.pool.join()
        self.update_ui_language() # 恢复窗口标题
        
        # 最后一次刷新日志队列
        self.master.after(100, self.check_log_queue)
        
        # 延迟显示总结，确保日志队列已完全清空
        self.master.after(200, self.show_summary)

    def show_summary(self):
        self.log('log_batch_complete')
        self.log('log_total_files', count=self.total_tasks)
        self.log('log_successful', count=self.successful_tasks)
        self.log('log_failed', count=self.failed_tasks)
        self.log('log_summary_line')

def main():
    multiprocessing.set_start_method("spawn", force=True)
    root = tk.Tk()
    app = Application(master=root)
    root.mainloop()

if __name__ == "__main__":
    main()
