import pydicom
import numpy as np
import os
from glob import glob
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from PIL import Image, ImageTk 

# --- DICOMデータ処理クラス ---
class DICOMDataLoader:
    def __init__(self):
        self.series_data = []
        self.header_info = {}
        self.is_loaded = False
        self.full_hu_volume = None 
        
    def load_series(self, folder_path):
        self.series_data = []
        self.header_info = {}
        self.is_loaded = False
        self.full_hu_volume = None
        
        dcm_files = glob(os.path.join(folder_path, '*.dcm'))
        
        if not dcm_files:
            return "エラー: 指定フォルダにDICOMファイルが見つかりません。", False

        try:
            sorted_files = self._sort_dicom_series(dcm_files)
        except Exception as e:
            return f"DICOMファイルのソート中にエラーが発生しました: {e}", False
            
        if not sorted_files:
            return "エラー: 有効な画像系列を特定できませんでした。", False

        try:
            self._process_data(sorted_files)
        except Exception as e:
            return f"HU値への変換中にエラーが発生しました: {e}", False

        if self.is_loaded:
            message = (f"DICOMシリーズを読み込みました。\n"
                       f"スライス数: {self.header_info.get('NumSlices')}\n"
                       f"画像サイズ: {self.header_info.get('Rows')}x{self.header_info.get('Columns')}")
            return message, True
        
        return "エラー: データの処理中に問題が発生しました。", False

    def _sort_dicom_series(self, dcm_files):
        series_map = {}
        for filepath in dcm_files:
            try:
                ds = pydicom.dcmread(filepath)
                # ファイルがPixel Dataを持たない場合はスキップ
                if 'PixelData' not in ds:
                    continue
                    
                key = ds.get('SeriesInstanceUID')
                z_pos = ds.get('ImagePositionPatient', [0, 0, 0])[2] 
                
                if key not in series_map:
                    series_map[key] = []
                series_map[key].append((z_pos, ds))
                
            except Exception:
                # DICOMファイルとして無効なファイルをスキップ
                continue
                
        if not series_map:
            return []
            
        main_series_uid = max(series_map, key=lambda k: len(series_map[k]))
        main_series = series_map[main_series_uid]
        
        main_series.sort(key=lambda x: x[0])
        return [item[1] for item in main_series]

    def _process_data(self, sorted_datasets):
        
        if not sorted_datasets:
            return
            
        ds0 = sorted_datasets[0]
        self.header_info = {
            'Rows': ds0.get('Rows', 0),
            'Columns': ds0.get('Columns', 0),
            'SliceThickness': ds0.get('SliceThickness', 1.0),
            'PixelSpacing': ds0.get('PixelSpacing', [1.0, 1.0]), 
            'NumSlices': 0, 
            'RescaleIntercept': ds0.get('RescaleIntercept', 0.0),
            'RescaleSlope': ds0.get('RescaleSlope', 1.0),
        }

        R_int = self.header_info['RescaleIntercept']
        R_slope = self.header_info['RescaleSlope']
        
        rows = self.header_info['Rows']
        cols = self.header_info['Columns']
        num_slices = len(sorted_datasets)

        self.full_hu_volume = np.zeros((num_slices, rows, cols), dtype=np.float32)
        
        all_hu_values = [] # 初期WL/WW設定のために全HU値を一時保存
        
        for i, ds in enumerate(sorted_datasets):
            pixel_array = ds.pixel_array.astype(np.int16) 
            hu_array = pixel_array * R_slope + R_int
            self.full_hu_volume[i] = hu_array
            all_hu_values.append(hu_array.ravel())
            
        self.header_info['NumSlices'] = num_slices
        self.is_loaded = True
        
        # Min/Max HU値の計算と初期値設定
        if all_hu_values:
            full_hu_array = np.concatenate(all_hu_values)
            min_hu = np.min(full_hu_array)
            max_hu = np.max(full_hu_array)
            self.header_info['MinHU'] = min_hu
            self.header_info['MaxHU'] = max_hu
        else:
            self.header_info['MinHU'] = 0.0
            self.header_info['MaxHU'] = 0.0
        
    def get_slice_data(self, view_plane, index):
        if not self.is_loaded:
            return None
            
        volume = self.full_hu_volume
        
        if view_plane == 'Axial':
            return volume[index, :, :]
        
        elif view_plane == 'Coronal':
            return volume[:, index, :]
            
        elif view_plane == 'Sagittal':
            return volume[:, :, index]

        return None
        
    def get_aspect_ratio(self, view_plane):
        if not self.is_loaded:
            return 1.0
            
        sy = self.header_info['PixelSpacing'][0]
        sx = self.header_info['PixelSpacing'][1]
        sz = self.header_info['SliceThickness']
        
        if view_plane == 'Axial':
            return sx / sy 
        elif view_plane == 'Coronal':
            return sx / sz 
        elif view_plane == 'Sagittal':
            return sy / sz 
            
        return 1.0

# --- Tkinter GUI クラス ---
class DICOMViewerApp:
    def __init__(self, master):
        self.master = master
        master.title("DICOM Viewer")
        master.geometry("1000x700")

        self.data_loader = DICOMDataLoader()
        self.current_slice = 0
        self.window_level = 40.0
        self.window_width = 400.0
        self.current_view = 'Axial'

        # マウスイベント処理用変数
        self.mouse_x = 0
        self.mouse_y = 0
        self.start_wl = self.window_level
        self.start_ww = self.window_width
        self.start_slice = self.current_slice

        # --- GUI レイアウト設定 (省略) ---
        main_frame = ttk.Frame(master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        control_frame = ttk.Frame(main_frame, width=300)
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        self.image_frame = ttk.Frame(main_frame)
        self.image_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.image_label = ttk.Label(self.image_frame, text="DICOM画像を読み込んでください")
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # --- マウスイベントのバインド ---
        self.image_label.bind("<Button-1>", self.on_mouse_down)
        self.image_label.bind("<B1-Motion>", self.on_mouse_drag)
        self.image_label.bind("<Button-3>", self.on_mouse_down_right)
        self.image_label.bind("<B3-Motion>", self.on_mouse_drag_right)
        self.image_label.bind("<MouseWheel>", self.on_mouse_wheel)
        self.image_label.bind("<Button-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.image_label.bind("<Button-5>", lambda e: self.on_mouse_wheel(e, -1))
        
        # --- コントロールパネルのウィジェット (省略) ---
        
        file_button = ttk.Button(control_frame, text="DICOMフォルダを選択", command=self.load_dicom_folder)
        file_button.pack(fill=tk.X, pady=5)
        
        self.status_label = ttk.Label(control_frame, text="未ロード", wraplength=280)
        self.status_label.pack(fill=tk.X, pady=5)
        
        view_group = ttk.LabelFrame(control_frame, text="表示断面切り替え", padding="10")
        view_group.pack(fill=tk.X, pady=10)
        
        self.view_var = tk.StringVar(value=self.current_view)
        
        ttk.Radiobutton(view_group, text="軸性断 (Axial)", variable=self.view_var, value='Axial', command=self.change_view).pack(anchor='w')
        ttk.Radiobutton(view_group, text="冠状断 (Coronal)", variable=self.view_var, value='Coronal', command=self.change_view).pack(anchor='w')
        ttk.Radiobutton(view_group, text="矢状断 (Sagittal)", variable=self.view_var, value='Sagittal', command=self.change_view).pack(anchor='w')
        
        header_group = ttk.LabelFrame(control_frame, text="DICOMヘッダー情報", padding="10")
        header_group.pack(fill=tk.X, pady=10)
        
        self.info_labels = {}
        info_keys = ['Rows', 'Columns', 'SliceThickness', 'NumSlices']
        for key in info_keys:
            label_text = {'Rows':'縦サイズ:', 'Columns':'横サイズ:', 
                          'SliceThickness':'スライス厚:', 'NumSlices':'スライス数:'}.get(key, key)
            
            ttk.Label(header_group, text=label_text).pack(anchor='w')
            self.info_labels[key] = ttk.Label(header_group, text="---")
            self.info_labels[key].pack(anchor='w', padx=10)

        param_group = ttk.LabelFrame(control_frame, text="画像コントラスト調整", padding="10")
        param_group.pack(fill=tk.X, pady=10)
        
        ttk.Label(param_group, text="Window Level (WL):").pack(anchor='w')
        self.wl_scale = ttk.Scale(param_group, from_=-3000, to=3000, command=self.update_parameters_from_scale) # 範囲を広げた
        self.wl_scale.set(self.window_level)
        self.wl_scale.pack(fill=tk.X)
        self.wl_label = ttk.Label(param_group, text=f"WL: {self.window_level:.1f}")
        self.wl_label.pack(anchor='w')

        ttk.Label(param_group, text="Window Width (WW):").pack(anchor='w', pady=(10, 0))
        self.ww_scale = ttk.Scale(param_group, from_=10, to=6000, command=self.update_parameters_from_scale) # 範囲を広げた
        self.ww_scale.set(self.window_width)
        self.ww_scale.pack(fill=tk.X)
        self.ww_label = ttk.Label(param_group, text=f"WW: {self.window_width:.1f}")
        self.ww_label.pack(anchor='w')

        slice_group = ttk.LabelFrame(control_frame, text="スライス切り替え", padding="10")
        slice_group.pack(fill=tk.X, pady=10)
        
        self.slice_label = ttk.Label(slice_group, text="スライス: 0 / 0")
        self.slice_label.pack(anchor='w')
        self.slice_scale = ttk.Scale(slice_group, from_=0, to=0, command=self.update_slice)
        self.slice_scale.pack(fill=tk.X)

    # --- WL/WW マウス調整メソッド (省略) ---
    def on_mouse_down(self, event):
        if self.data_loader.is_loaded:
            self.mouse_x = event.x
            self.mouse_y = event.y
            self.start_wl = self.window_level
            self.start_ww = self.window_width

    def on_mouse_drag(self, event):
        if self.data_loader.is_loaded:
            dx = event.x - self.mouse_x
            dy = event.y - self.mouse_y
            
            WL_SENSITIVITY = 2.0
            WW_SENSITIVITY = 4.0
            
            new_wl = self.start_wl - dy * WL_SENSITIVITY
            new_ww = self.start_ww + dx * WW_SENSITIVITY
            
            self.window_width = max(10.0, new_ww)
            self.window_level = new_wl
            
            self._update_wl_ww_gui()
            self.update_image()
            
    def _update_wl_ww_gui(self):
        self.wl_scale.set(self.window_level)
        self.ww_scale.set(self.window_width)
        self.wl_label.config(text=f"WL: {self.window_level:.1f}")
        self.ww_label.config(text=f"WW: {self.window_width:.1f}")

    # --- スライス マウス調整メソッド (省略) ---
    def on_mouse_down_right(self, event):
        if self.data_loader.is_loaded:
            self.mouse_y = event.y
            self.start_slice = self.current_slice

    def on_mouse_drag_right(self, event):
        if self.data_loader.is_loaded:
            dy = event.y - self.mouse_y
            
            SLICE_SENSITIVITY = 10
            
            slice_delta = -int(dy / SLICE_SENSITIVITY)
            new_slice = self.start_slice + slice_delta
            
            self.set_current_slice(new_slice)

    def on_mouse_wheel(self, event, mac_direction=None):
        if not self.data_loader.is_loaded:
            return
            
        if mac_direction is not None:
            delta = mac_direction
        elif event.delta:
            delta = int(event.delta / 120) 
        else:
            return

        new_slice = self.current_slice + delta
        self.set_current_slice(new_slice)
        
    def set_current_slice(self, new_slice):
        max_index = self.get_max_slice_index(self.current_view)
        
        clamped_slice = max(0, min(max_index, new_slice))
        
        if clamped_slice != self.current_slice:
            self.current_slice = clamped_slice
            self.slice_scale.set(self.current_slice)
            
            max_index = self.get_max_slice_index(self.current_view)
            self.slice_label.config(text=f"スライス: {self.current_slice + 1} / {max_index + 1}")
            self.update_image()

    # --- その他のメソッド ---

    def load_dicom_folder(self):
        folder_path = filedialog.askdirectory(title="DICOMファイルを含むフォルダを選択")
        if folder_path:
            message, success = self.data_loader.load_series(folder_path)
            self.status_label.config(text=message)
            
            if success:
                self.current_view = self.view_var.get()
                
                # --- 初期WL/WW設定 ---
                min_hu = self.data_loader.header_info.get('MinHU', -1000)
                max_hu = self.data_loader.header_info.get('MaxHU', 1000)
                
                # HU値の範囲全体を初期WL/WWとする
                self.window_level = (max_hu + min_hu) / 2
                self.window_width = max(10.0, max_hu - min_hu)
                
                self._update_wl_ww_gui()
                self._update_gui_after_load()
                self.set_current_slice(0)
            else:
                # ロード失敗時のGUIリセット
                self.slice_scale.config(to=0)
                self.slice_scale.set(0)
                self.slice_label.config(text="スライス: 0 / 0")

    def _update_gui_after_load(self):
        info = self.data_loader.header_info
        
        for key in self.info_labels:
            value = info.get(key, '---')
            if key == 'SliceThickness':
                 self.info_labels[key].config(text=f"{value:.2f} mm")
            else:
                 self.info_labels[key].config(text=f"{value}")
            
        self.reset_slice_scale()

    def get_max_slice_index(self, view_plane):
        info = self.data_loader.header_info
        if view_plane == 'Axial':
            return info.get('NumSlices', 1) - 1
        elif view_plane == 'Coronal':
            return info.get('Rows', 1) - 1
        elif view_plane == 'Sagittal':
            return info.get('Columns', 1) - 1
        return 0

    def reset_slice_scale(self):
        max_index = self.get_max_slice_index(self.current_view)
        
        self.slice_scale.config(from_=0, to=max_index)
        
        if self.current_slice > max_index:
            self.current_slice = 0
            
        self.slice_scale.set(self.current_slice)
        self.slice_label.config(text=f"スライス: {self.current_slice + 1} / {max_index + 1}")
        self.update_image()

    def change_view(self):
        if self.data_loader.is_loaded:
            self.current_view = self.view_var.get()
            self.reset_slice_scale()

    def update_parameters_from_scale(self, *args):
        self.window_level = self.wl_scale.get()
        self.window_width = self.ww_scale.get()
        self.wl_label.config(text=f"WL: {self.window_level:.1f}")
        self.ww_label.config(text=f"WW: {self.window_width:.1f}")
        if self.data_loader.is_loaded:
            self.update_image()

    def update_slice(self, *args):
        new_slice = int(self.slice_scale.get())
        if new_slice != self.current_slice:
            self.set_current_slice(new_slice)

    def update_image(self):
        hu_data = self.data_loader.get_slice_data(self.current_view, self.current_slice)
        
        if hu_data is None:
            self.image_label.config(text="画像データが見つかりません。")
            return

        # 1. HU値からグレースケール値へのマッピング (WL/WW処理)
        W = self.window_width
        L = self.window_level
        
        min_val = L - W / 2
        max_val = L + W / 2
        
        image_data = hu_data.copy()
        image_data[image_data < min_val] = min_val
        image_data[image_data > max_val] = max_val
        
        image_data = (image_data - min_val) / W * 255.0
        image_data = image_data.astype(np.uint8)
        
        # 2. Pillowへの変換とアスペクト比の補正
        img = Image.fromarray(image_data, mode='L')
        aspect_ratio = self.data_loader.get_aspect_ratio(self.current_view)
        
        img_width, img_height = img.size
        frame_width = self.image_frame.winfo_width() - 20
        frame_height = self.image_frame.winfo_height() - 20
        
        if frame_width > 0 and frame_height > 0:
            
            if frame_width / frame_height > aspect_ratio:
                target_height = frame_height
                target_width = int(target_height * aspect_ratio)
            else:
                target_width = frame_width
                target_height = int(target_width / aspect_ratio)

            if target_width > 0 and target_height > 0:
                img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        # 3. Tkinterでの描画
        self.tk_img = ImageTk.PhotoImage(image=img)
        
        self.image_label.config(image=self.tk_img, text="")
        self.image_label.image = self.tk_img
        self.image_label.pack_configure(expand=True)
        
# --- メイン実行部分 ---
if __name__ == "__main__":
    root = tk.Tk()
    app = DICOMViewerApp(root)
    root.bind('<Configure>', lambda e: app.update_image() if app.data_loader.is_loaded else None)
    root.mainloop()