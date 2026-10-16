import io

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Production URL cua workflow n8n "Chan doan benh ca" (workflow phai o trang thai Active)
N8N_WEBHOOK_URL = "https://n8n.n2nai.io/webhook/chan-doan-benh-ca"

# Kich thuoc toi da cua anh truoc khi gui di (giup gui nhanh hon)
KICH_THUOC_TOI_DA = 1280

# Ten tieng Viet ngan va mau khung cho tung loai benh
NHAN_BENH = {
    "aeromoniasis": ("Lở loét Aeromonas", "#e63946"),
    "gill_disease": ("Bệnh mang", "#f4a261"),
    "red_disease": ("Đốm đỏ", "#d62828"),
    "fungal": ("Nấm thủy mi", "#3a86ff"),
    "parasitic": ("Ký sinh trùng", "#8338ec"),
    "white_tail": ("Trắng đuôi", "#2a9d8f"),
}

MUC_DO = {
    "nhe": ("Nhẹ", "🟢"),
    "trung_binh": ("Trung bình", "🟠"),
    "nang": ("Nặng", "🔴"),
}

st.set_page_config(page_title="Phát hiện bệnh trên da cá", page_icon="🐟")


def chuan_bi_anh(file_bytes: bytes) -> Image.Image:
    """Mo anh, xoay dung chieu theo EXIF va thu nho neu qua lon."""
    anh = Image.open(io.BytesIO(file_bytes))
    anh = ImageOps.exif_transpose(anh).convert("RGB")
    anh.thumbnail((KICH_THUOC_TOI_DA, KICH_THUOC_TOI_DA))
    return anh


def anh_sang_jpeg(anh: Image.Image) -> bytes:
    buf = io.BytesIO()
    anh.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def lay_font(co_chu: int):
    try:
        return ImageFont.load_default(size=co_chu)
    except TypeError:  # Pillow cu khong ho tro tham so size
        return ImageFont.load_default()


def ve_khung(anh: Image.Image, predictions: list, rong_goc: float, cao_goc: float) -> Image.Image:
    """Ve khung quanh tung vet benh. Toa do Roboflow la tam khung (x, y) + rong/cao."""
    ket_qua = anh.copy()
    ve = ImageDraw.Draw(ket_qua)
    he_so_x = anh.width / rong_goc if rong_goc else 1
    he_so_y = anh.height / cao_goc if cao_goc else 1
    do_day = max(2, anh.width // 250)
    font = lay_font(max(14, anh.width // 40))

    for p in predictions:
        x, y = p["x"] * he_so_x, p["y"] * he_so_y
        w, h = p["width"] * he_so_x, p["height"] * he_so_y
        # Gioi han khung trong pham vi anh
        trai, tren = max(0, x - w / 2), max(0, y - h / 2)
        phai, duoi = min(anh.width - 1, x + w / 2), min(anh.height - 1, y + h / 2)
        mau = NHAN_BENH.get(p["class"], (p["class"], "#ff006e"))[1]
        ve.rectangle([trai, tren, phai, duoi], outline=mau, width=do_day)

        # Nhan ghi tren khung (dung ten lop khong dau de font mac dinh hien thi duoc)
        nhan = f"{p['class']} {p['confidence']:.0%}"
        khung_chu = ve.textbbox((0, 0), nhan, font=font)
        rong_chu, cao_chu = khung_chu[2] - khung_chu[0], khung_chu[3] - khung_chu[1]
        cao_nhan = cao_chu + 8
        # Dat nhan phia tren khung; neu sat mep tren cua anh thi dat ben trong khung
        tren_nhan = tren - cao_nhan if tren - cao_nhan >= 0 else tren
        ve.rectangle([trai, tren_nhan, trai + rong_chu + 8, tren_nhan + cao_nhan], fill=mau)
        ve.text((trai + 4, tren_nhan + 4 - khung_chu[1]), nhan, fill="white", font=font)
    return ket_qua


def hien_thi_ket_qua(kq: dict, anh: Image.Image) -> None:
    if kq.get("trang_thai") != "ok":
        st.image(anh, caption="Ảnh đã gửi", width="stretch")
        st.success(
            kq.get(
                "thong_bao",
                "Không phát hiện vết bệnh. Cá có thể khỏe mạnh, hoặc ảnh chưa đủ rõ.",
            )
        )
        return

    predictions = kq.get("predictions") or []
    anh_ve = ve_khung(anh, predictions, kq.get("image_width") or anh.width, kq.get("image_height") or anh.height)
    st.image(anh_ve, caption="Vùng tổn thương được phát hiện", width="stretch")

    ma_benh = kq.get("ma_benh", "")
    ten_benh = kq.get("ten_benh") or NHAN_BENH.get(ma_benh, (ma_benh, ""))[0]
    do_tin_cay = min(max(float(kq.get("do_tin_cay") or 0), 0.0), 1.0)
    muc_do, bieu_tuong = MUC_DO.get(kq.get("muc_do"), ("Không rõ", "⚪"))

    st.error(f"🦠 Phát hiện: **{ten_benh}**")
    cot1, cot2, cot3 = st.columns(3)
    cot1.metric("Độ tin cậy", f"{do_tin_cay:.0%}")
    cot2.metric("Số vết bệnh", kq.get("so_vet_benh", len(predictions)))
    cot3.metric("Mức độ (ước lượng)", f"{bieu_tuong} {muc_do}")
    st.progress(do_tin_cay)

    cac_benh = kq.get("cac_benh") or []
    if len(cac_benh) > 1:
        st.warning(
            "Ảnh có dấu hiệu của nhiều bệnh: "
            + ", ".join(
                f"{NHAN_BENH.get(b['class'], (b['class'], ''))[0]} ({b['so_vet']} vết)" for b in cac_benh
            )
        )

    st.subheader("🔎 Nguyên nhân")
    st.write(kq.get("nguyen_nhan", ""))
    st.subheader("🐟 Triệu chứng")
    st.write(kq.get("trieu_chung", ""))
    st.subheader("💊 Cách xử lý")
    st.write(kq.get("cach_xu_ly", ""))
    st.subheader("🛡️ Phòng ngừa")
    st.write(kq.get("phong_ngua", ""))


st.title("🐟 Phát hiện bệnh trên da cá")
st.write(
    "Tải lên hoặc chụp ảnh **cá nước ngọt** (thấy rõ thân cá) để hệ thống khoanh vùng vết bệnh "
    "và gợi ý cách xử lý."
)

tab_tai_len, tab_chup = st.tabs(["📁 Tải ảnh lên", "📷 Chụp ảnh"])
with tab_tai_len:
    anh_tai_len = st.file_uploader("Chọn ảnh cá (JPG, PNG)", type=["jpg", "jpeg", "png"])
with tab_chup:
    anh_chup = st.camera_input("Chụp ảnh cá")

tep_anh = anh_tai_len or anh_chup

if tep_anh is None:
    st.info("👆 Hãy tải lên hoặc chụp một ảnh cá để bắt đầu.")
else:
    try:
        anh = chuan_bi_anh(tep_anh.getvalue())
    except Exception:
        st.error("Không đọc được ảnh. Vui lòng chọn ảnh JPG hoặc PNG khác.")
        st.stop()

    st.image(anh, caption="Ảnh đã chọn", width="stretch")

    if st.button("🔍 Phát hiện bệnh", type="primary"):
        with st.spinner("Đang phân tích ảnh..."):
            try:
                files = {"file": ("anh_ca.jpg", anh_sang_jpeg(anh), "image/jpeg")}
                phan_hoi = requests.post(N8N_WEBHOOK_URL, files=files, timeout=90)
                phan_hoi.raise_for_status()
                ket_qua = phan_hoi.json()
            except requests.exceptions.Timeout:
                st.error("Máy chủ phản hồi quá lâu. Vui lòng thử lại sau.")
                st.stop()
            except requests.exceptions.RequestException as loi:
                st.error(f"Không kết nối được tới máy chủ chẩn đoán: {loi}")
                st.stop()
            except ValueError:
                st.error("Máy chủ trả về dữ liệu không hợp lệ.")
                st.stop()

        hien_thi_ket_qua(ket_qua, anh)

    st.divider()
    st.caption(
        "⚠️ Kết quả chỉ mang tính tham khảo. Trước khi dùng thuốc hoặc hóa chất, "
        "hãy hỏi ý kiến cán bộ thú y thủy sản tại địa phương."
    )
