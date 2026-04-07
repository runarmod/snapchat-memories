import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import downloader
import exif_utils
import snap_utils
import video_utils
import zip_utils

# Optional dependencies: detect availability via module specs
HAS_PIL = importlib.util.find_spec("PIL.Image") is not None
HAS_PIEXIF = HAS_PIL and importlib.util.find_spec("piexif") is not None

# For setting video metadata without ffmpeg
HAS_MUTAGEN = importlib.util.find_spec("mutagen.mp4") is not None

# For video conversion (HEVC to H.264)
HAS_PYAV = importlib.util.find_spec("av") is not None

# For VLC-based video conversion
HAS_VLC = importlib.util.find_spec("vlc") is not None

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for verbose logging
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),  # Log to a file
        logging.StreamHandler(),  # Log to console
    ],
)


# Windows-specific subprocess flag to prevent command windows from popping up
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def parse_date(date_str):
    """Parse date string from JSON format to datetime object. Delegates to snap_utils."""
    return snap_utils.parse_date(date_str)


def parse_location(location_str):
    """Parse location string to get latitude and longitude. Delegates to snap_utils."""
    return snap_utils.parse_location(location_str)


def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds format for EXIF. Delegates to snap_utils."""
    return snap_utils.decimal_to_dms(decimal)


def set_image_exif_metadata(
    file_path, date_obj, latitude, longitude, timezone_offset=None
):
    """Set EXIF metadata for image files. Delegates to exif_utils."""
    return exif_utils.set_image_exif_metadata(
        file_path, date_obj, latitude, longitude, timezone_offset
    )


def check_ffmpeg():
    """Check if ffmpeg is available on the system. Delegates to video_utils."""
    return video_utils.check_ffmpeg()


def check_vlc():
    """Check if VLC Python bindings are available. Delegates to video_utils."""
    return video_utils.check_vlc()


def find_vlc_executable():
    """Find VLC executable on the system. Delegates to video_utils."""
    return video_utils.find_vlc_executable()


def convert_with_vlc(input_path, output_path=None):
    """Convert video using VLC - delegated to video_utils."""
    return video_utils.convert_with_vlc(input_path, output_path)


def convert_with_vlc_python(input_path, output_path):
    """Convert video using VLC Python bindings - delegated to video_utils."""
    return video_utils.convert_with_vlc_python(input_path, output_path)


def convert_with_vlc_subprocess(input_path, output_path):
    """Convert video using VLC command-line interface via subprocess."""
    return video_utils.convert_with_vlc_subprocess(input_path, output_path)


def set_video_metadata(file_path, date_obj, latitude, longitude, timezone_offset=None):
    """Set metadata for video files. Delegates to video_utils."""
    return video_utils.set_video_metadata(
        file_path, date_obj, latitude, longitude, timezone_offset
    )


def set_video_metadata_ffmpeg(
    file_path, date_obj, latitude, longitude, timezone_offset=None
):
    """Set video metadata using ffmpeg if available. Delegates to video_utils."""
    return video_utils.set_video_metadata_ffmpeg(
        file_path, date_obj, latitude, longitude, timezone_offset
    )


def set_file_timestamps(file_path, date_obj):
    """Set file modification and access times. Delegates to snap_utils."""
    return snap_utils.set_file_timestamps(file_path, date_obj)


def enforce_portrait_video(file_path, timeout=300):
    """Ensure the video is portrait (height >= width). Delegates to video_utils."""
    return video_utils.enforce_portrait_video(file_path, timeout)


def convert_hevc_to_h264(
    input_path,
    output_path=None,
    max_attempts=3,
    failed_dir_path="downloads/failed_conversions",
):
    """Convert any video to H.264 for better compatibility. Delegates to video_utils."""
    return video_utils.convert_hevc_to_h264(
        input_path, output_path, max_attempts, failed_dir_path
    )


def extract_media_from_zip(zip_path, output_path):
    """Extract media file from ZIP archive. Delegates to zip_utils."""
    return zip_utils.extract_media_from_zip(zip_path, output_path)


def merge_images(main_img_path, overlay_img_path, output_path):
    """Merge overlay image on top of main image and save to output_path. Delegates to zip_utils."""
    return zip_utils.merge_images(main_img_path, overlay_img_path, output_path)


def merge_video_overlay(main_video_path, overlay_image_path, output_path):
    """Overlay an image on top of a video using ffmpeg. Delegates to zip_utils."""
    return zip_utils.merge_video_overlay(
        main_video_path, overlay_image_path, output_path
    )


def process_zip_overlay(zip_path, output_dir, date_obj=None):
    """Process ZIP overlay files. Delegates to zip_utils."""
    return zip_utils.process_zip_overlay(zip_path, output_dir, date_obj)


def download_media(
    url,
    output_path,
    max_retries=3,
    progress_callback=None,
    date_obj=None,
    merge_overlay=True,
):
    """Download media with retry mechanism. Delegates to downloader."""
    return downloader.download_media(
        url, output_path, max_retries, progress_callback, date_obj, merge_overlay
    )


def validate_downloaded_file(file_path):
    """Validate downloaded file. Delegates to snap_utils."""
    return snap_utils.validate_downloaded_file(file_path)


def get_file_extension(media_type):
    """Get file extension for media type. Delegates to snap_utils."""
    return snap_utils.get_file_extension(media_type)


class ScrollableFrame(ttk.Frame):
    """A scrollable frame that allows vertical scrolling of its content."""

    def __init__(self, container, *args, **kwargs):
        super().__init__(container)
        # Canvas for scrolling
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)

        # Pack canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.v_scrollbar.pack(side="right", fill="y")

        # Inner frame where widgets should be placed
        self.frame = ttk.Frame(self.canvas, *args, **kwargs)
        self._window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        # Update scrollregion when inner frame changes size
        self.frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        # Make inner window width match canvas width
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width),
        )

        # Mouse wheel support (Windows / macOS typical behavior)
        def _on_mousewheel(event):
            try:
                delta = int(-1 * (event.delta / 120))
            except Exception:
                delta = 0
            if delta:
                self.canvas.yview_scroll(delta, "units")

        # Bind mousewheel to the canvas
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)


class SnapchatDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Snapchat Memories Downloader")
        self.root.geometry("1000x800")
        self.root.resizable(True, True)
        self.root.minsize(900, 700)

        # Variables
        self.json_path = tk.StringVar()
        self.output_path = tk.StringVar(value="downloads")
        # Conversion is automatic when tools are available; no checkbox in UI
        self.max_retries = tk.IntVar(
            value=3
        )  # Number of download attempts (initial + retries)
        default_threads = 3
        self.max_threads = tk.IntVar(value=default_threads)
        self.is_downloading = False
        self.stop_download = False

        # Timezone preference variable
        self.use_gps_tz = tk.BooleanVar(value=True)  # Use GPS for timezone by default

        # Overlay merge preference: "merge" = overlay only, "original" = original only, "both" = save both
        self.overlay_mode = tk.StringVar(value="merge")

        # Configure style
        self.setup_styles()

        # Build UI
        self.create_widgets()

        # Center window
        self.center_window()

        # Setup cleanup handler for orphaned processes
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start(self):
        self.root.mainloop()

    def setup_styles(self):
        """Configure ttk styles for a modern look."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Modern palette
        bg_color = "#f4f7fb"  # app background
        card_bg = "#ffffff"
        primary_color = "#2168f3"  # primary blue
        accent_color = "#7c5cff"  # accent
        success_color = "#00b894"
        text_color = "#2b3440"
        muted_color = "#6c757d"

        # Apply root background
        self.root.configure(bg=bg_color)

        # Card and main frame styles
        style.configure("Main.TFrame", background=bg_color)
        style.configure("Card.TFrame", background=card_bg, relief="flat", borderwidth=1)

        # Label styles
        style.configure(
            "Title.TLabel",
            background=card_bg,
            foreground=text_color,
            font=("Segoe UI", 18, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=card_bg,
            foreground=muted_color,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=card_bg,
            foreground=text_color,
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Info.TLabel",
            background=card_bg,
            foreground=muted_color,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background=card_bg,
            foreground=text_color,
            font=("Segoe UI", 9),
        )

        # Button styles
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(12, 8),
            foreground="white",
            background=primary_color,
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", accent_color),
                ("!active", primary_color),
                ("disabled", "#cbd5e1"),
            ],
            foreground=[("disabled", "#f1f5f9")],
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            padding=(8, 6),
            foreground=primary_color,
            background=card_bg,
        )

        style.configure(
            "Stop.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(8, 6),
            foreground="white",
            background="#e74c3c",
        )
        style.map(
            "Stop.TButton",
            background=[
                ("active", "#c0392b"),
                ("!active", "#e74c3c"),
                ("disabled", "#f1f5f9"),
            ],
            foreground=[("disabled", "#f1f5f9")],
        )

        # Progressbar style: slimmer and colored
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor=card_bg,
            background=success_color,
            thickness=14,
        )

        # Checkbutton style: match card background
        style.configure(
            "Card.TCheckbutton",
            background=card_bg,
            foreground=text_color,
            font=("Segoe UI", 9),
        )
        style.map("Card.TCheckbutton", background=[("active", card_bg)])

        # Radiobutton style (matches card background)
        style.configure(
            "Card.TRadiobutton",
            background=card_bg,
            foreground=text_color,
            font=("Segoe UI", 9),
        )
        style.map("Card.TRadiobutton", background=[("active", card_bg)])

        # Small helper used across widgets for consistent padding
        self._card_padding = 16

    def center_window(self):
        """Center the window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        """Create and layout all widgets."""
        # Main container (scrollable)
        scroll_container = ScrollableFrame(self.root, style="Main.TFrame", padding=20)
        scroll_container.pack(fill=tk.BOTH, expand=True)
        main_frame = scroll_container.frame

        # Header card
        header_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        header_card.pack(fill=tk.X, pady=(0, 20))

        title_label = ttk.Label(
            header_card, text="Snapchat Memories Downloader", style="Title.TLabel"
        )
        title_label.pack(anchor=tk.W)

        subtitle_label = ttk.Label(
            header_card,
            text="Download your Snapchat memories with metadata preservation",
            style="Subtitle.TLabel",
        )
        subtitle_label.pack(anchor=tk.W, pady=(5, 0))

        # Input card
        input_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        input_card.pack(fill=tk.X, pady=(0, 20))

        # JSON file selection
        json_label = ttk.Label(input_card, text="JSON File", style="Header.TLabel")
        json_label.pack(anchor=tk.W, pady=(0, 8))

        json_frame = ttk.Frame(input_card, style="Card.TFrame")
        json_frame.pack(fill=tk.X, pady=(0, 15))

        self.json_entry = ttk.Entry(
            json_frame, textvariable=self.json_path, font=("Segoe UI", 9), width=50
        )
        self.json_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        json_btn = ttk.Button(
            json_frame,
            text="Browse...",
            command=self.browse_json,
            style="Secondary.TButton",
        )
        json_btn.pack(side=tk.LEFT)

        json_info = ttk.Label(
            input_card,
            text="Select your memories_history.json file from Snapchat export",
            style="Info.TLabel",
        )
        json_info.pack(anchor=tk.W, pady=(0, 15))

        # Output directory selection
        output_label = ttk.Label(
            input_card, text="Output Directory", style="Header.TLabel"
        )
        output_label.pack(anchor=tk.W, pady=(0, 8))

        output_frame = ttk.Frame(input_card, style="Card.TFrame")
        output_frame.pack(fill=tk.X, pady=(0, 15))

        self.output_entry = ttk.Entry(
            output_frame, textvariable=self.output_path, font=("Segoe UI", 9), width=50
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        output_btn = ttk.Button(
            output_frame,
            text="Browse...",
            command=self.browse_output,
            style="Secondary.TButton",
        )
        output_btn.pack(side=tk.LEFT)

        # Open output directory button (next to Browse)
        open_out_btn = ttk.Button(
            output_frame,
            text="Open",
            command=self.open_output_dir,
            style="Secondary.TButton",
            width=8,
        )
        open_out_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Open debug log button
        open_log_btn = ttk.Button(
            output_frame,
            text="Open Log",
            command=self.open_debug_log,
            style="Secondary.TButton",
            width=10,
        )
        open_log_btn.pack(side=tk.LEFT, padx=(8, 0))

        output_info = ttk.Label(
            input_card,
            text="Choose where to save your downloaded memories",
            style="Info.TLabel",
        )
        output_info.pack(anchor=tk.W, pady=(0, 15))

        # Conversion tools status (ffmpeg / VLC) with install links if missing
        tools_frame = ttk.Frame(input_card, style="Card.TFrame")
        tools_frame.pack(fill=tk.X, pady=(0, 20))

        tools_header = ttk.Label(
            tools_frame, text="Conversion Tools", style="Header.TLabel"
        )
        tools_header.pack(anchor=tk.W)

        # ffmpeg status
        ffmpeg_installed = check_ffmpeg()
        ffmpeg_text = (
            "✓ ffmpeg installed"
            if ffmpeg_installed
            else "⚠ ffmpeg not found — click to download"
        )
        ffmpeg_label = ttk.Label(
            tools_frame,
            text=ffmpeg_text,
            style="Info.TLabel",
            cursor=("hand2" if not ffmpeg_installed else "arrow"),
        )
        ffmpeg_label.pack(anchor=tk.W, padx=(6, 0))
        if not ffmpeg_installed:
            ffmpeg_label.bind(
                "<Button-1>",
                lambda e: webbrowser.open("https://ffmpeg.org/download.html"),
            )

        # VLC status
        vlc_path = find_vlc_executable()
        vlc_installed = bool(vlc_path or HAS_VLC)
        if vlc_installed and vlc_path:
            vlc_text = f"✓ VLC installed ({vlc_path})"
        elif HAS_VLC:
            vlc_text = "✓ VLC Python bindings available"
        else:
            vlc_text = "⚠ VLC not found — click to download"
        vlc_label = ttk.Label(
            tools_frame,
            text=vlc_text,
            style="Info.TLabel",
            cursor=("hand2" if not vlc_installed else "arrow"),
        )
        vlc_label.pack(anchor=tk.W, padx=(6, 0))
        if not vlc_installed:
            vlc_label.bind(
                "<Button-1>", lambda e: webbrowser.open("https://www.videolan.org/vlc/")
            )

        info_label = ttk.Label(
            tools_frame,
            text=(
                "Videos will be converted to H.264 automatically when tools are available. "
                "ffmpeg/VLC are also used to merge Snapchat captions back onto photos or videos; "
                "click the links to download."
            ),
            style="Info.TLabel",
            wraplength=520,
            justify=tk.LEFT,
        )
        info_label.pack(anchor=tk.W, pady=(6, 0))
        # Update wraplength dynamically so the text wraps with the frame width
        tools_frame.bind(
            "<Configure>",
            lambda e: info_label.config(wraplength=max(e.width - 12, 200)),
        )

        # Small action buttons to open the download pages for ffmpeg and VLC
        download_buttons_frame = ttk.Frame(tools_frame, style="Card.TFrame")
        download_buttons_frame.pack(anchor=tk.W, pady=(8, 0))

        ffmpeg_btn_text = "Open ffmpeg" if ffmpeg_installed else "Download ffmpeg"
        ffmpeg_btn = ttk.Button(
            download_buttons_frame,
            text=ffmpeg_btn_text,
            style="Secondary.TButton",
            width=18,
            command=lambda: webbrowser.open("https://ffmpeg.org/download.html"),
        )
        ffmpeg_btn.pack(side=tk.LEFT, padx=(6, 8))

        vlc_btn_text = "Open VLC" if vlc_installed else "Download VLC"
        vlc_btn = ttk.Button(
            download_buttons_frame,
            text=vlc_btn_text,
            style="Secondary.TButton",
            width=18,
            command=lambda: webbrowser.open("https://www.videolan.org/vlc/"),
        )
        vlc_btn.pack(side=tk.LEFT)

        # Download retries option
        retries_frame = ttk.Frame(input_card, style="Card.TFrame")
        retries_frame.pack(fill=tk.X, pady=(8, 12))

        retries_label = ttk.Label(
            retries_frame, text="Download Retries:", style="Header.TLabel"
        )
        retries_label.pack(side=tk.LEFT)

        # Use a Spinbox for retry count
        retries_spin = tk.Spinbox(
            retries_frame, from_=1, to=10, width=5, textvariable=self.max_retries
        )
        retries_spin.pack(side=tk.LEFT, padx=(8, 0))

        retries_info = ttk.Label(
            input_card,
            text="Number of download attempts (initial try + retries)",
            style="Info.TLabel",
        )
        retries_info.pack(anchor=tk.W, pady=(6, 10))

        # Download threads option
        threads_frame = ttk.Frame(input_card, style="Card.TFrame")
        threads_frame.pack(fill=tk.X, pady=(0, 12))

        threads_label = ttk.Label(
            threads_frame, text="Multi-Download Count:", style="Header.TLabel"
        )
        threads_label.pack(side=tk.LEFT)

        threads_spin = tk.Spinbox(
            threads_frame, from_=1, to=16, width=5, textvariable=self.max_threads
        )
        threads_spin.pack(side=tk.LEFT, padx=(8, 0))

        threads_info = ttk.Label(
            input_card,
            text="Number of concurrent downloads (higher uses more bandwidth/CPU)",
            style="Info.TLabel",
        )
        threads_info.pack(anchor=tk.W, pady=(6, 10))

        # Resume Options Section
        resume_header = ttk.Label(
            input_card, text="Resume Options", style="Header.TLabel"
        )
        resume_header.pack(anchor=tk.W, pady=(15, 8))

        # Skip existing files checkbox
        self.skip_existing = tk.BooleanVar(value=False)
        skip_check = ttk.Checkbutton(
            input_card,
            text="Skip existing files (resume mode)",
            variable=self.skip_existing,
            style="Card.TCheckbutton",
            command=self._toggle_reconvert_visibility,
        )
        skip_check.pack(anchor=tk.W, padx=(6, 0))

        skip_info = ttk.Label(
            input_card,
            text="Validates local files before downloading. Useful for resuming interrupted sessions or adding new memories.",
            style="Info.TLabel",
        )
        skip_info.pack(anchor=tk.W, padx=(26, 0), pady=(2, 8))

        # Re-convert videos checkbox (hidden by default, shown when skip_existing is ON)
        self.reconvert_frame = ttk.Frame(input_card, style="Card.TFrame")
        # Don't pack yet - will be shown/hidden by _toggle_reconvert_visibility

        self.reconvert_videos = tk.BooleanVar(value=False)
        reconvert_check = ttk.Checkbutton(
            self.reconvert_frame,
            text="Re-convert existing videos to H.264 if needed",
            variable=self.reconvert_videos,
            style="Card.TCheckbutton",
        )
        reconvert_check.pack(anchor=tk.W, padx=(20, 0))

        reconvert_info = ttk.Label(
            self.reconvert_frame,
            text="Checks codec of existing videos and re-converts non-H.264 videos for better compatibility",
            style="Info.TLabel",
        )
        reconvert_info.pack(anchor=tk.W, padx=(46, 0), pady=(2, 8))

        # Timezone options section
        tz_header = ttk.Label(
            input_card, text="Timezone Handling", style="Header.TLabel"
        )
        tz_header.pack(anchor=tk.W, pady=(15, 8))

        gps_tz_check = ttk.Checkbutton(
            input_card,
            text="Use GPS coordinates to determine local timezone (recommended)",
            variable=self.use_gps_tz,
            style="Card.TCheckbutton",
        )
        gps_tz_check.pack(anchor=tk.W, padx=(6, 0))

        gps_tz_info = ttk.Label(
            input_card,
            text="Uses photo/video GPS location to detect local timezone. Files are named and timestamped with local time.\nWhen disabled or GPS unavailable, uses system timezone as fallback.",
            style="Info.TLabel",
        )
        gps_tz_info.pack(anchor=tk.W, padx=(26, 0), pady=(2, 8))

        # Overlay merge option — radio buttons for 3 modes
        overlay_header = ttk.Label(
            input_card, text="Snap Overlay / Caption", style="Header.TLabel"
        )
        overlay_header.pack(anchor=tk.W, pady=(15, 8))

        overlay_rb_merge = ttk.Radiobutton(
            input_card,
            text="With overlay only — merge captions/stickers onto media",
            variable=self.overlay_mode,
            value="merge",
            style="Card.TRadiobutton",
        )
        overlay_rb_merge.pack(anchor=tk.W, padx=(6, 0))

        overlay_rb_original = ttk.Radiobutton(
            input_card,
            text="Original only — save photo/video without overlay",
            variable=self.overlay_mode,
            value="original",
            style="Card.TRadiobutton",
        )
        overlay_rb_original.pack(anchor=tk.W, padx=(6, 0), pady=(4, 0))

        overlay_rb_both = ttk.Radiobutton(
            input_card,
            text="Both versions — save original AND overlay in the same folder",
            variable=self.overlay_mode,
            value="both",
            style="Card.TRadiobutton",
        )
        overlay_rb_both.pack(anchor=tk.W, padx=(6, 0), pady=(4, 0))

        overlay_info = ttk.Label(
            input_card,
            text="Controls how Snapchat captions and stickers are handled.\n"
            "'Both versions' saves the clean original and the overlay version side-by-side.",
            style="Info.TLabel",
        )
        overlay_info.pack(anchor=tk.W, padx=(26, 0), pady=(2, 8))

        # Check available conversion tools and display status
        # conversion_status = self.get_conversion_status()
        # conversion_info = ttk.Label(input_card,
        #                            text=conversion_status,
        #                            style="Info.TLabel")
        # conversion_info.pack(anchor=tk.W, pady=(0, 20))

        # Buttons
        button_frame = ttk.Frame(input_card, style="Card.TFrame")
        button_frame.pack(fill=tk.X)

        self.download_btn = ttk.Button(
            button_frame,
            text="Start Download",
            command=self.start_download,
            style="Primary.TButton",
        )
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(
            button_frame,
            text="⏹ Stop",
            command=self.stop_download_func,
            style="Stop.TButton",
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 10))

        # DEV TESTING: Test ZIP overlay button
        # self.test_zip_btn = ttk.Button(button_frame, text="🧪 Test ZIP Overlay",
        #                                command=self.test_zip_overlay,
        #                                style="Secondary.TButton")
        # self.test_zip_btn.pack(side=tk.LEFT)

        # Progress card
        self.progress_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        self.progress_card.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

        progress_label = ttk.Label(
            self.progress_card, text="Download Progress", style="Header.TLabel"
        )
        progress_label.pack(anchor=tk.W, pady=(0, 15))

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.progress_card,
            style="Custom.Horizontal.TProgressbar",
            mode="determinate",
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        # Status label
        self.status_label = ttk.Label(
            self.progress_card, text="Ready to download", style="Status.TLabel"
        )
        self.status_label.pack(anchor=tk.W, pady=(0, 10))

        # Log area
        log_frame = ttk.Frame(self.progress_card, style="Card.TFrame")
        log_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Allow the log area to resize with the window by not forcing a fixed height
        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#f8f9fa",
            fg="#2f3542",
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

    def _toggle_reconvert_visibility(self):
        """Show or hide the re-convert option based on skip_existing checkbox state."""
        if self.skip_existing.get():
            self.reconvert_frame.pack(
                anchor=tk.W,
                pady=(0, 8),
                after=self.reconvert_frame.master.winfo_children()[
                    list(self.reconvert_frame.master.winfo_children()).index(
                        self.reconvert_frame
                    )
                    - 1
                    if self.reconvert_frame
                    in self.reconvert_frame.master.winfo_children()
                    else -1
                ]
                if self.reconvert_frame.winfo_ismapped()
                else None,
            )
            # Simple approach: just pack it
            self.reconvert_frame.pack(anchor=tk.W, pady=(0, 8))
        else:
            self.reconvert_frame.pack_forget()
            self.reconvert_videos.set(False)  # Reset when hidden

    def browse_json(self):
        """Open file dialog to select JSON file."""
        filename = filedialog.askopenfilename(
            title="Select Snapchat Memories JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if filename:
            self.json_path.set(filename)

    def browse_output(self):
        """Open dialog to select output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_path.set(directory)

    def open_output_dir(self):
        """Open the currently selected output directory in the system file manager."""
        path = self.output_path.get() or "downloads"
        if not os.path.exists(path):
            messagebox.showwarning("Folder not found", f"Directory not found: {path}")
            return
        try:
            # Windows
            if os.name == "nt":
                os.startfile(path)
                return
            # macOS / Linux fallback to file URL open
            webbrowser.open(f"file://{os.path.abspath(path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")

    def open_debug_log(self):
        """Open the debug.log file with the default text editor."""
        log_path = "debug.log"
        if not os.path.exists(log_path):
            messagebox.showinfo(
                "Log Not Found",
                "debug.log doesn't exist yet. It will be created when you start a download.",
            )
            return
        try:
            # Windows - open with default text editor
            if os.name == "nt":
                os.startfile(log_path)
                return
            # macOS
            if sys.platform == "darwin":
                subprocess.run(["open", log_path])
                return
            # Linux
            subprocess.run(["xdg-open", log_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open debug.log: {e}")

    def get_conversion_status(self):
        """Check what conversion tools are available and return status message."""
        tools = []

        if HAS_PYAV:
            tools.append("PyAV")

        vlc_exe = find_vlc_executable()
        if vlc_exe or HAS_VLC:
            tools.append("VLC")

        if not tools:
            return (
                "⚠ No conversion tools found. Videos will be downloaded in original format.\n"
                "Install PyAV (pip install av) or VLC (https://www.videolan.org/) for H.264 conversion."
            )

        tools_str = " & ".join(tools)
        return f"✓ Conversion available via {tools_str}. Videos will be converted to H.264 for Windows compatibility."

    def log(self, message):
        """Add message to log area."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def update_progress(self, current, total, is_resume_mode=False):
        """Update progress bar.

        Args:
            current: Current item number
            total: Total items
            is_resume_mode: If True, show 'Validating' instead of 'Downloading'
        """
        progress = (current / total) * 100
        self.progress_bar["value"] = progress
        if is_resume_mode:
            self.status_label.config(
                text=f"🔍 Validating {current} of {total}...", foreground="#00d2d3"
            )
        else:
            self.status_label.config(
                text=f"⬇ Downloading {current} of {total}...", foreground="#00d2d3"
            )
        self.root.update_idletasks()

    def start_download(self):
        """Start the download process."""
        if self.is_downloading:
            return

        json_file = self.json_path.get()
        output_dir = self.output_path.get()

        if not json_file:
            messagebox.showerror("Error", "Please select a JSON file")
            return

        if not os.path.exists(json_file):
            messagebox.showerror("Error", f"JSON file not found: {json_file}")
            return

        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory")
            return

        # Clear log
        self.log_text.delete(1.0, tk.END)

        # Update UI state with visual feedback
        self.is_downloading = True
        self.stop_download = False

        # Show appropriate button text based on mode
        if self.skip_existing.get():
            self.download_btn.config(state=tk.DISABLED, text="🔍 Validating...")
            self.status_label.config(
                text="🔍 Validating existing files...", foreground="#00d2d3"
            )
        else:
            self.download_btn.config(state=tk.DISABLED, text="⏳ Downloading...")
            self.status_label.config(
                text="🔄 Starting download...", foreground="#00d2d3"
            )

        self.stop_btn.config(state=tk.NORMAL)
        self.progress_bar["value"] = 0

        # Start download in separate thread
        thread = threading.Thread(
            target=self.download_thread, args=(json_file, output_dir)
        )
        thread.daemon = True
        thread.start()

    def stop_download_func(self):
        """Stop the download process."""
        self.stop_download = True
        self.stop_btn.config(state=tk.DISABLED, text="⏹ Stopping...")
        self.status_label.config(text="⚠ Stopping download...", foreground="#f39c12")
        self.log("⚠ Stopping download...")

    def test_zip_overlay(self):
        """Test ZIP overlay processing with a selected file."""
        # Open file dialog to select ZIP
        zip_file = filedialog.askopenfilename(
            title="Select ZIP file to test overlay processing",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            initialdir=os.path.join(os.getcwd(), "test files"),
        )

        if not zip_file:
            return

        if not os.path.exists(zip_file):
            messagebox.showerror("Error", f"ZIP file not found: {zip_file}")
            return

        # Get output directory
        output_dir = self.output_path.get()
        if not output_dir:
            output_dir = "downloads"

        # Clear log and show processing message
        self.log_text.delete(1.0, tk.END)
        self.log("=" * 50)
        self.log("Testing ZIP Overlay Processing")
        self.log(f"ZIP File: {zip_file}")
        self.log(f"Output: {output_dir}")
        self.log("=" * 50)
        self.log("")

        # Disable button during processing
        self.test_zip_btn.config(state=tk.DISABLED, text="🔄 Processing...")
        self.status_label.config(
            text="🔄 Processing ZIP overlay...", foreground="#00d2d3"
        )

        # Run in separate thread to keep GUI responsive
        thread = threading.Thread(
            target=self.test_zip_thread, args=(zip_file, output_dir)
        )
        thread.daemon = True
        thread.start()

    def test_zip_thread(self, zip_file, output_dir):
        """Process ZIP overlay in background thread."""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)

            # Process the ZIP file
            self.log("Processing ZIP file for overlays...")
            self.log("(This may take a while for large videos)")
            self.log("")
            merged_files = process_zip_overlay(zip_file, output_dir, date_obj=None)

            if merged_files:
                self.log("")
                self.log(
                    f"✓ Successfully processed {len(merged_files)} merged file(s):"
                )
                for merged_file in merged_files:
                    self.log(f"  • {os.path.basename(merged_file)}")
                self.log("")
                self.log(f"Output location: {output_dir}")
                self.status_label.config(
                    text="✅ ZIP processing complete", foreground="#27ae60"
                )
                messagebox.showinfo(
                    "Success",
                    f"Successfully processed ZIP overlay!\n\n"
                    f"Created {len(merged_files)} merged file(s) in:\n{output_dir}",
                )
            else:
                self.log("")
                self.log("⚠ No overlay pairs found in ZIP file")
                self.log("  (Looking for files ending with -main and -overlay)")
                self.status_label.config(
                    text="⚠ No overlays found", foreground="#f39c12"
                )
                messagebox.showwarning(
                    "No Overlays",
                    "No overlay pairs found in ZIP file.\n\n"
                    "ZIP should contain files like:\n"
                    "• filename-main.mp4\n"
                    "• filename-overlay.png",
                )

        except Exception as e:
            self.log("")
            self.log(f"✗ Error processing ZIP: {e}")
            logging.error(f"ZIP overlay test error: {e}", exc_info=True)
            self.status_label.config(
                text="✗ ZIP processing failed", foreground="#e74c3c"
            )
            messagebox.showerror("Error", f"Failed to process ZIP overlay:\n\n{str(e)}")

        finally:
            self.log("")
            self.log("=" * 50)
            # Re-enable button
            self.test_zip_btn.config(state=tk.NORMAL, text="🧪 Test ZIP Overlay")

    def cleanup_temp_files(self, output_path):
        """Clean up orphaned temporary files from previous interrupted runs.

        Args:
            output_path (Path): Output directory to scan for temp files

        Note:
            Removes files matching patterns:
            - *.temp.mp4 (video conversion temps)
            - *.backup (metadata backup files)
            - *.rotated.* (portrait rotation temps)
            - *.exif.tmp (EXIF metadata temps)
            - *.zip (downloaded ZIP overlays)
        """
        temp_patterns = ["*.temp.mp4", "*.backup", "*.rotated.*", "*.exif.tmp", "*.zip"]

        cleaned_count = 0
        for pattern in temp_patterns:
            for temp_file in output_path.glob(pattern):
                try:
                    temp_file.unlink()
                    cleaned_count += 1
                    logging.debug(f"Removed temp file: {temp_file.name}")
                except Exception as e:
                    logging.warning(f"Could not remove temp file {temp_file}: {e}")

        if cleaned_count > 0:
            self.log(
                f"🧹 Cleaned up {cleaned_count} temporary file(s) from previous run"
            )

    def should_skip_download(
        self, item, output_path, idx, date_obj, date_obj_local, extension
    ):
        """Determine if file download should be skipped because it already exists locally.

        Args:
            item (dict): JSON item with media metadata
            output_path (Path): Output directory path
            idx (int): Item index for filename generation
            date_obj (datetime): Parsed UTC date object (for backward compatibility checks)
            date_obj_local (datetime): Parsed local timezone date object (for new downloads)
            extension (str): File extension (.jpg, .mp4, etc.)

        Returns:
            tuple: (should_skip: bool, existing_path: str or None, skip_reason: str)
                   If should_skip is True, existing_path contains the found file path

        Note:
            This function checks multiple filename patterns because Snapchat ZIP overlay
            files are merged and renamed to different formats:
            - Normal downloads: YYYYMMDD_HHMMSS_idx.ext (e.g., 20230815_143022_628.mp4)
            - Merged overlays: YYYYMMDD_HHMMSS.ext (without idx)
            - Collision resolved: YYYYMMDD_HHMMSS_1.ext, _2.ext, etc.

            The ambiguity means we cannot definitively know which pattern a given JSON
            item will create, so we check all possibilities and skip if ANY valid file exists.

            For timezone compatibility, checks both:
            - Local timezone pattern (new behavior): files named with local time
            - UTC timezone pattern (legacy): files downloaded before timezone fix
        """
        # Generate both local and UTC formatted dates for backward compatibility
        date_formatted_local = date_obj_local.strftime("%Y%m%d_%H%M%S")
        date_formatted_utc = date_obj.strftime("%Y%m%d_%H%M%S")

        # We'll check patterns for both local (preferred) and UTC (legacy) timestamps
        date_patterns = [date_formatted_local]
        if date_formatted_utc != date_formatted_local:  # Only check UTC if different
            date_patterns.append(date_formatted_utc)

        # Check 1: Normal download filename (YYYYMMDD_HHMMSS_idx.ext)
        # Check both local and UTC patterns for backward compatibility
        for date_formatted in date_patterns:
            normal_filename = f"{date_formatted}_{idx}{extension}"
            normal_path = output_path / normal_filename
            if normal_path.exists():
                if validate_downloaded_file(str(normal_path)):
                    return True, str(normal_path), "normal download"
                else:
                    logging.warning(
                        f"Found invalid existing file, will re-download: {normal_path}"
                    )
                    return False, None, "invalid file"

            # Check 2: Merged overlay filename (YYYYMMDD_HHMMSS.ext) - no idx suffix
            # This pattern is created when ZIP files contain -main/-overlay pairs
            merged_base = f"{date_formatted}{extension}"
            merged_path = output_path / merged_base
            if merged_path.exists():
                if validate_downloaded_file(str(merged_path)):
                    return True, str(merged_path), "merged overlay"
                else:
                    logging.warning(
                        f"Found invalid merged file, will re-download: {merged_path}"
                    )
                    return False, None, "invalid merged"

            # Check 3: Collision-resolved merged files (YYYYMMDD_HHMMSS_1.ext, _2.ext, ...)
            # When multiple overlays have the same timestamp, counter suffixes are added
            for count in range(1, 11):  # Reasonable upper bound
                collision_name = f"{date_formatted}_{count}{extension}"
                collision_path = output_path / collision_name
                if collision_path.exists():
                    if validate_downloaded_file(str(collision_path)):
                        return (
                            True,
                            str(collision_path),
                            f"collision-resolved merge (_{count})",
                        )
                    else:
                        logging.warning(
                            f"Found invalid collision file, will re-download: {collision_path}"
                        )
                        return False, None, "invalid collision"

        # Check 4: Failed conversions directory (use local timezone pattern)
        normal_filename_local = f"{date_formatted_local}_{idx}{extension}"
        failed_path = output_path / "failed_conversions" / normal_filename_local
        if failed_path.exists():
            # Conservative: skip files that previously failed conversion
            # User can manually delete from failed_conversions/ to retry
            return True, str(failed_path), "previously failed conversion"

        # No existing file found - proceed with download
        return False, None, "not found"

    def check_video_codec(self, file_path):
        """Check if video file is encoded with H.264 codec using PyAV.

        Args:
            file_path (str): Path to video file

        Returns:
            tuple: (is_h264: bool, codec_name: str or None)
                   is_h264 is True if video uses H.264/AVC codec

        Note:
            Uses PyAV (if available) to detect codec. Returns (False, None) if
            PyAV is not available or file cannot be opened.
        """
        if not HAS_PYAV:
            logging.debug("PyAV not available for codec detection")
            return False, None

        try:
            import av

            container = av.open(str(file_path))
            if container.streams.video:
                codec_name = container.streams.video[0].codec_context.name
                container.close()
                # H.264 is also known as AVC
                is_h264 = codec_name.lower() in ["h264", "avc", "avc1"]
                return is_h264, codec_name
            container.close()
        except Exception as e:
            logging.debug(f"Could not detect codec for {file_path}: {e}")

        return False, None

    def process_media_item(self, idx, total, item, output_path, max_retries):
        # Check if stop was requested before processing
        if self.stop_download:
            return ([f"[{idx}/{total}] Cancelled"], False, False)

        logs = [f"[{idx}/{total}] Processing..."]

        def log_local(message):
            logs.append(message)

        def progress_callback(message):
            log_local(f"  {message}")

        try:
            # Extract metadata
            date_str = item.get("Date", "")
            media_type = item.get("Media Type", "Unknown")
            location_str = item.get("Location", "")
            download_url = item.get("Media Download Url", "")

            if not download_url:
                log_local("  ⚠ No download URL found, skipping")
                return logs, False, True

            # Parse date and location
            try:
                date_obj = parse_date(date_str)
            except Exception:
                log_local("  ⚠ Invalid date format, skipping")
                return logs, False, True

            latitude, longitude = parse_location(location_str)

            # Log location data for debugging
            if latitude is not None and longitude is not None:
                log_local(f"  📍 Location: {latitude}, {longitude}")
            else:
                log_local("  📍 No location data available")

            # Convert UTC to local timezone using GPS coordinates or system timezone
            try:
                # Only force system timezone if GPS option is disabled
                # (fallback preference is used automatically when GPS lookup fails)
                force_system_tz = not self.use_gps_tz.get()

                local_dt, tz_name, tz_offset = snap_utils.convert_to_local_timezone(
                    date_obj, latitude, longitude, force_system_tz=force_system_tz
                )
                date_obj_local = local_dt  # Use local time for filenames and metadata
                log_local(f"  🌍 Timezone: {tz_name} ({tz_offset})")
            except Exception as e:
                logging.warning(f"Timezone conversion failed, using UTC: {e}")
                date_obj_local = date_obj
                tz_offset = "+00:00"

            # Generate filename
            date_formatted = date_obj_local.strftime("%Y%m%d_%H%M%S")
            extension = get_file_extension(media_type)
            filename = f"{date_formatted}_{idx}{extension}"
            file_path = output_path / filename

            log_local(f"  File: {filename}")
            log_local(f"  Type: {media_type}")

            # Check if we should skip download (resume mode)
            skip_download = False
            existing_file_path = None
            if self.skip_existing.get():
                should_skip, existing_path, skip_reason = self.should_skip_download(
                    item, output_path, idx, date_obj, date_obj_local, extension
                )
                if should_skip:
                    skip_download = True
                    existing_file_path = existing_path
                    log_local(f"  ⏭ Skipped download (file exists: {skip_reason})")

                    # Update file_path to point to existing file for metadata processing
                    file_path = Path(existing_file_path)

                    # Check if we should re-convert video
                    if media_type == "Video" and self.reconvert_videos.get():
                        is_h264, codec_name = self.check_video_codec(str(file_path))
                        if not is_h264 and codec_name:
                            log_local(
                                f"  🔄 Video needs re-conversion (current: {codec_name})"
                            )
                            skip_download = False  # Force conversion by not skipping
                            existing_file_path = None
                        elif is_h264:
                            log_local("  ✓ Video already in H.264 format")

            # Download file (or skip if already exists)
            if not skip_download:
                # Check stop flag before starting download
                if self.stop_download:
                    log_local("  ⚠ Cancelled by user")
                    return logs, False, False

                download_success, merged_files = download_media(
                    download_url,
                    str(file_path),
                    max_retries=max_retries,
                    progress_callback=progress_callback,
                    date_obj=date_obj,
                    merge_overlay=self.overlay_mode.get(),
                )

                if download_success:
                    log_local("  ✓ Downloaded")

                    # Handle "both" mode: dict with merged list + original path
                    # Handle "merge" mode: list of merged file paths
                    # Handle "original" mode: None (fall through to single file processing)
                    both_mode_original = None
                    overlay_file_list = None

                    if isinstance(merged_files, dict):
                        # "Both" mode return: {"merged": [...], "original": "path"}
                        overlay_file_list = merged_files.get("merged", [])
                        both_mode_original = merged_files.get("original")
                        log_local(
                            f"  ℹ Both mode: {len(overlay_file_list)} overlay file(s) + original"
                        )
                    elif isinstance(merged_files, list) and merged_files:
                        # "Merge" mode return: list of merged paths
                        overlay_file_list = merged_files

                    if overlay_file_list:
                        log_local(
                            f"  ℹ Processing {len(overlay_file_list)} merged file(s) from ZIP overlay"
                        )
                        for merged_file in overlay_file_list:
                            merged_path = Path(merged_file)
                            log_local(f"  📄 {merged_path.name}")

                            # Determine if it's a video or image
                            ext = merged_path.suffix.lower()
                            is_video = ext in [".mp4", ".mov", ".m4v", ".avi", ".mkv"]

                            if is_video:
                                # Set video metadata - try ffmpeg first for better compatibility, then mutagen
                                metadata_set = False

                                # Try ffmpeg first (sets standard creation_time metadata)
                                try:
                                    if set_video_metadata_ffmpeg(
                                        str(merged_path),
                                        date_obj_local,
                                        latitude,
                                        longitude,
                                        tz_offset,
                                    ):
                                        log_local("    ✓ Set video metadata (ffmpeg)")
                                        metadata_set = True
                                except Exception as ffmpeg_error:
                                    log_local(
                                        f"    ℹ ffmpeg metadata setting failed, trying mutagen: {ffmpeg_error}"
                                    )

                                # Fall back to mutagen if ffmpeg didn't work
                                if not metadata_set and HAS_MUTAGEN:
                                    try:
                                        if set_video_metadata(
                                            str(merged_path),
                                            date_obj_local,
                                            latitude,
                                            longitude,
                                            tz_offset,
                                        ):
                                            log_local(
                                                "    ✓ Set video metadata (mutagen)"
                                            )
                                            metadata_set = True
                                    except Exception as metadata_error:
                                        log_local(
                                            f"    ⚠ Metadata error: {metadata_error}"
                                        )

                                if not metadata_set:
                                    log_local(
                                        "    ℹ Video metadata not set (install ffmpeg or mutagen)"
                                    )

                                set_file_timestamps(str(merged_path), date_obj_local)
                                log_local("    ✓ Set file timestamps")
                            else:
                                # Set image metadata
                                if HAS_PIEXIF and ext in [".jpg", ".jpeg"]:
                                    try:
                                        set_image_exif_metadata(
                                            str(merged_path),
                                            date_obj_local,
                                            latitude,
                                            longitude,
                                            tz_offset,
                                        )
                                        log_local("    ✓ Set EXIF metadata")
                                    except Exception as exif_error:
                                        log_local(
                                            f"    ⚠ EXIF metadata error: {exif_error}"
                                        )
                                set_file_timestamps(str(merged_path), date_obj_local)
                                log_local("    ✓ Set file timestamps")

                        # In "both" mode, also process the original file
                        if both_mode_original and os.path.exists(both_mode_original):
                            log_local(
                                f"  📄 Processing original (no overlay): {Path(both_mode_original).name}"
                            )
                            # The original was extracted to file_path by the downloader.
                            # Fall through to single-file metadata processing below
                            # (don't return early like merge-only mode)
                        else:
                            # Merge-only mode: return after overlay processing
                            return logs, True, False

                    # Set metadata for single file (original-only download or "both" mode original)
                    if media_type == "Image" and extension.lower() in [".jpg", ".jpeg"]:
                        if HAS_PIEXIF:
                            try:
                                set_image_exif_metadata(
                                    str(file_path),
                                    date_obj_local,
                                    latitude,
                                    longitude,
                                    tz_offset,
                                )
                                log_local("  ✓ Set EXIF metadata")
                            except Exception as exif_error:
                                log_local(f"  ⚠ EXIF metadata error: {exif_error}")
                        # Always set file timestamps for images
                        set_file_timestamps(str(file_path), date_obj_local)
                    elif media_type == "Video":
                        # Check stop flag before conversion
                        if self.stop_download:
                            log_local("  ⚠ Cancelled during conversion")
                            return logs, False, False

                        # Convert all videos to H.264 by default
                        log_local("  🔄 Converting to H.264...")

                        # Check if any conversion tool is available
                        if not HAS_PYAV and not find_vlc_executable() and not HAS_VLC:
                            log_local(
                                "  ⚠ No conversion tools available - keeping original format"
                            )
                            log_local(
                                "  ℹ Install PyAV (pip install av) or VLC for automatic H.264 conversion"
                            )
                            # Still count as success - video was downloaded
                        else:
                            # Pass the custom failed_dir path
                            failed_conversions_dir = str(
                                output_path / "failed_conversions"
                            )
                            try:
                                success, result = convert_hevc_to_h264(
                                    str(file_path),
                                    failed_dir_path=failed_conversions_dir,
                                )
                                if success:
                                    log_local("  ✓ Converted to H.264")
                                    # Replace original with converted file
                                    try:
                                        os.remove(str(file_path))
                                        os.rename(result, str(file_path))
                                        # CRITICAL: Set timestamps AFTER file replacement
                                        set_file_timestamps(
                                            str(file_path), date_obj_local
                                        )
                                        log_local("  ✓ Set file timestamps")
                                    except Exception as rename_error:
                                        log_local(
                                            f"  ⚠ Could not replace original: {rename_error}"
                                        )
                                        # If replacement failed but conversion succeeded, still set timestamps on original
                                        set_file_timestamps(
                                            str(file_path), date_obj_local
                                        )
                                else:
                                    log_local(f"  ⚠ Conversion failed: {result}")
                                    # Don't count as error - file is still downloaded in original format
                                    # Set timestamps on original file
                                    set_file_timestamps(str(file_path), date_obj_local)
                            except Exception as conversion_error:
                                log_local(f"  ⚠ Conversion error: {conversion_error}")
                                # Ensure timestamps are set even if conversion crashes
                                set_file_timestamps(str(file_path), date_obj_local)

                        # Try to set video metadata - use ffmpeg first for better compatibility, then mutagen
                        metadata_set = False

                        # Try ffmpeg first (sets standard creation_time metadata)
                        try:
                            if set_video_metadata_ffmpeg(
                                str(file_path),
                                date_obj_local,
                                latitude,
                                longitude,
                                tz_offset,
                            ):
                                log_local("  ✓ Set video metadata (ffmpeg)")
                                metadata_set = True
                        except Exception as ffmpeg_error:
                            logging.debug(
                                f"ffmpeg metadata setting failed: {ffmpeg_error}"
                            )

                        # Fall back to mutagen if ffmpeg didn't work
                        if not metadata_set and HAS_MUTAGEN:
                            try:
                                if set_video_metadata(
                                    str(file_path),
                                    date_obj_local,
                                    latitude,
                                    longitude,
                                    tz_offset,
                                ):
                                    log_local("  ✓ Set video metadata (mutagen)")
                                    metadata_set = True
                            except Exception as metadata_error:
                                log_local(f"  ⚠ Metadata error: {metadata_error}")

                        if not metadata_set:
                            log_local(
                                "  ℹ Video downloaded (install ffmpeg or mutagen for embedded metadata)"
                            )

                    # ALWAYS set file timestamps as final step for any media type
                    # This ensures the creation/modification date is correct even if other metadata fails
                    try:
                        set_file_timestamps(str(file_path), date_obj_local)
                        log_local("  ✓ File date set correctly")
                    except Exception as timestamp_error:
                        log_local(
                            f"  ⚠ Failed to set file timestamps: {timestamp_error}"
                        )

                    # Validate the downloaded file
                    try:
                        if not validate_downloaded_file(str(file_path)):
                            log_local("  ⚠ Downloaded file is corrupted or incomplete")
                            return logs, False, True
                    except Exception as validation_error:
                        log_local(f"  ⚠ Validation error: {validation_error}")

                    return logs, True, False

                else:
                    log_local("  ✗ Download failed")
                    return logs, False, True

            else:
                # File was skipped - check and update metadata if needed
                log_local("  📋 Checking existing file metadata...")
                metadata_updated = False

                # Set metadata based on file type
                if media_type == "Image" and extension.lower() in [".jpg", ".jpeg"]:
                    if HAS_PIEXIF:
                        try:
                            # Check if EXIF update is needed by attempting to set
                            # The function returns True if metadata was written
                            if set_image_exif_metadata(
                                str(file_path),
                                date_obj_local,
                                latitude,
                                longitude,
                                tz_offset,
                            ):
                                log_local("  ✓ Updated EXIF metadata")
                                metadata_updated = True
                            else:
                                log_local("  ℹ EXIF metadata already present")
                        except Exception as exif_error:
                            log_local(f"  ⚠ EXIF metadata error: {exif_error}")
                    else:
                        log_local("  ℹ EXIF not available (piexif not installed)")
                elif media_type == "Video":
                    # Set video metadata - try ffmpeg first, then mutagen
                    video_metadata_set = False

                    try:
                        if set_video_metadata_ffmpeg(
                            str(file_path),
                            date_obj_local,
                            latitude,
                            longitude,
                            tz_offset,
                        ):
                            log_local("  ✓ Updated video metadata (ffmpeg)")
                            video_metadata_set = True
                            metadata_updated = True
                    except Exception as ffmpeg_error:
                        logging.debug(f"ffmpeg metadata setting failed: {ffmpeg_error}")

                    if not video_metadata_set and HAS_MUTAGEN:
                        try:
                            if set_video_metadata(
                                str(file_path),
                                date_obj_local,
                                latitude,
                                longitude,
                                tz_offset,
                            ):
                                log_local("  ✓ Updated video metadata (mutagen)")
                                video_metadata_set = True
                                metadata_updated = True
                        except Exception as metadata_error:
                            log_local(f"  ⚠ Metadata error: {metadata_error}")

                    if not video_metadata_set:
                        log_local(
                            "  ℹ Video metadata not updated (install ffmpeg or mutagen)"
                        )

                # Check and set file timestamps
                try:
                    current_mtime = os.path.getmtime(str(file_path))
                    expected_mtime = date_obj_local.timestamp()
                    # Only update if timestamp differs by more than 1 second
                    if abs(current_mtime - expected_mtime) > 1:
                        set_file_timestamps(str(file_path), date_obj_local)
                        log_local("  ✓ Updated file timestamps")
                        metadata_updated = True
                    else:
                        log_local("  ℹ File timestamps already correct")
                except Exception as timestamp_error:
                    log_local(
                        f"  ⚠ Failed to check/set file timestamps: {timestamp_error}"
                    )

                if not metadata_updated:
                    log_local("  ✓ All metadata already correct")

                # File skip counts as success
                return logs, True, False

        except Exception as item_error:
            log_local(f"  ✗ Error processing item: {item_error}")
            logging.error(f"Error processing item {idx}: {item_error}", exc_info=True)
            return logs, False, True

    def download_thread(self, json_file, output_dir):
        """Download process running in separate thread."""
        try:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)

            # Load JSON
            self.log(f"Loading JSON from: {json_file}")
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Get media items
            media_items = data.get("Saved Media", [])
            total = len(media_items)
            self.log(f"Found {total} media items to download\n")

            if total == 0:
                self.log("⚠ No media items found in JSON file")
                self.download_complete()
                return

            # Clean up temp files if resume mode is enabled
            if self.skip_existing.get():
                self.log("🔄 Resume mode enabled - checking for existing files")
                self.cleanup_temp_files(output_path)

            # Log timezone settings
            if self.use_gps_tz.get():
                self.log(
                    "🌍 Timezone mode: Using GPS coordinates (falls back to system timezone)"
                )
            else:
                self.log("🌍 Timezone mode: Using system/fallback timezone")

            # Log overlay mode
            overlay_mode = self.overlay_mode.get()
            overlay_labels = {
                "merge": "With overlay only",
                "original": "Original only (no overlay)",
                "both": "Both versions (original + overlay)",
            }
            self.log(
                f"🖼 Overlay mode: {overlay_labels.get(overlay_mode, overlay_mode)}"
            )

            # Process each item
            success_count = 0
            skipped_count = 0
            error_count = 0
            has_started_downloading = False

            max_retries = self.max_retries.get()
            max_workers = max(1, min(self.max_threads.get(), total))
            self.log(f"Using {max_workers} download thread(s)\n")

            items_iter = iter(enumerate(media_items, 1))
            futures = {}
            completed_count = 0
            stop_logged = False
            executor = None

            def submit_next():
                try:
                    idx, item = next(items_iter)
                except StopIteration:
                    return False

                future = executor.submit(
                    self.process_media_item, idx, total, item, output_path, max_retries
                )
                futures[future] = idx
                return True

            executor = ThreadPoolExecutor(max_workers=max_workers)
            try:
                while len(futures) < max_workers and submit_next():
                    pass

                while futures:
                    # Use timeout to prevent indefinite blocking
                    done, _ = wait(futures, return_when=FIRST_COMPLETED, timeout=1.0)

                    # Check stop flag even if no tasks completed
                    if self.stop_download and not done:
                        if not stop_logged:
                            self.log("\n⚠ Download stopped by user")
                            stop_logged = True
                        # Cancel all remaining futures
                        for pending_future in list(futures.keys()):
                            pending_future.cancel()
                        break

                    for future in done:
                        idx = futures.pop(future)
                        completed_count += 1

                        try:
                            logs, success, error = future.result()
                        except Exception as item_error:
                            logs = [
                                f"[{idx}/{total}] Processing...",
                                f"  ✗ Error processing item: {item_error}",
                            ]
                            logging.error(
                                f"Error processing item {idx}: {item_error}",
                                exc_info=True,
                            )
                            success = False
                            error = True

                        for line in logs:
                            self.log(line)

                        # Check if this was a skip or actual download
                        was_skipped = any("⏭ Skipped" in line for line in logs)

                        if success:
                            if was_skipped:
                                skipped_count += 1
                            else:
                                # Actual download occurred
                                if not has_started_downloading:
                                    has_started_downloading = True
                                    # Switch UI to downloading state
                                    self.download_btn.config(text="⬇ Downloading...")
                            success_count += 1
                        if error:
                            error_count += 1

                        # Update progress with detailed status
                        downloaded_count = success_count - skipped_count
                        is_resume = self.skip_existing.get()

                        # Only show "Validating" status if we are in resume mode AND haven't started downloading yet
                        show_validating_status = (
                            is_resume and not has_started_downloading
                        )

                        if show_validating_status:
                            # Show detailed breakdown in resume mode
                            self.status_label.config(
                                text=f"✓ Validated: {completed_count}/{total} | ⬇ New: {downloaded_count} | ⏭ Skipped: {skipped_count} | ✗ Failed: {error_count}",
                                foreground="#00d2d3",
                            )

                        self.update_progress(
                            completed_count,
                            total,
                            is_resume_mode=show_validating_status,
                        )
                        self.log("")  # Empty line

                        if self.stop_download and not stop_logged:
                            self.log("\n⚠ Download stopped by user")
                            stop_logged = True

                    if self.stop_download:
                        # Cancel all remaining futures
                        for pending_future in list(futures.keys()):
                            pending_future.cancel()
                        break  # Exit the loop immediately

                    while len(futures) < max_workers and submit_next():
                        pass
            finally:
                # Shutdown executor without waiting for running tasks when stopped
                if self.stop_download:
                    # Try to use cancel_futures if available (Python 3.9+)
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        # Older Python versions don't have cancel_futures parameter
                        executor.shutdown(wait=False)
                    self.log("⚡ Forcefully stopped - some tasks cancelled")
                else:
                    executor.shutdown(wait=True)

            # Final summary
            downloaded_count = success_count - skipped_count
            self.log("=" * 50)
            self.log("Download Complete!")
            if self.skip_existing.get():
                self.log(f"Downloaded: {downloaded_count}")
                self.log(f"Skipped: {skipped_count}")
            else:
                self.log(f"Success: {success_count}")
            self.log(f"Failed: {error_count}")
            self.log(f"Total: {total}")
            self.log(f"Output: {output_dir}")
            self.log("=" * 50)

            if not self.stop_download:
                if self.skip_existing.get():
                    messagebox.showinfo(
                        "Complete",
                        f"Downloaded {downloaded_count} files\n"
                        f"Skipped {skipped_count} existing files\n"
                        f"Failed {error_count} files\n"
                        f"Output: {output_dir}",
                    )
                else:
                    messagebox.showinfo(
                        "Complete",
                        f"Downloaded {success_count} of {total} files\n"
                        f"Output: {output_dir}",
                    )

        except Exception as e:
            self.log(f"\n✗ Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")

        finally:
            self.download_complete()

    def download_complete(self):
        """Reset UI after download completes."""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL, text="Start Download")
        self.stop_btn.config(state=tk.DISABLED, text="⏹ Stop")
        if self.stop_download:
            self.status_label.config(text="⚠ Download stopped", foreground="#f39c12")
        else:
            self.status_label.config(text="✅ Download complete", foreground="#27ae60")

    def cleanup_ffmpeg_processes(self):
        """Kill any orphaned ffmpeg processes."""
        try:
            if sys.platform == "win32":
                # Use taskkill on Windows to terminate ffmpeg processes
                subprocess.run(
                    ["taskkill", "/F", "/IM", "ffmpeg.exe"],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
                logging.info("Cleaned up any orphaned ffmpeg processes")
            else:
                # On Unix-like systems, use pkill
                subprocess.run(["pkill", "-9", "ffmpeg"], capture_output=True)
                logging.info("Cleaned up any orphaned ffmpeg processes")
        except Exception as e:
            # Silently fail if no ffmpeg processes exist or cleanup fails
            logging.debug(f"ffmpeg cleanup: {e}")

    def on_closing(self):
        """Handle application close event."""
        # Clean up any orphaned ffmpeg processes
        self.cleanup_ffmpeg_processes()

        # Stop any ongoing downloads
        if self.is_downloading:
            self.stop_download = True
            logging.info("Download stopped due to application close")

        # Destroy the window
        self.root.destroy()


# ==================== Main ====================


def main():
    """Main function to run the GUI."""
    root = tk.Tk()
    app = SnapchatDownloaderGUI(root)
    app.start()


if __name__ == "__main__":
    main()
