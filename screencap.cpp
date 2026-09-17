// language: C++, file: screencap.cpp, target: Windows 10/11, MSVC x64
// *GDI: BitBlt full desktop → HBITMAP → GDI+ JPEG/PNG*
// *DXGI: Desktop Duplication API → ID3D11Texture2D → staging → CPU read → encode*
// *multi-monitor via virtual screen coords (GDI) or per-output duplication (DXGI)*
// *compile: cl /std:c++17 /EHsc /O2 screencap.cpp gdiplus.lib d3d11.lib dxgi.lib ole32.lib*

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <gdiplus.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <string>
#include <vector>
#include <chrono>
#include <thread>
#include <cstdio>

#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "ole32.lib")

using Microsoft::WRL::ComPtr;

// ============ GDI capture ============

// returns HBITMAP of full virtual screen; caller deletes
HBITMAP gdi_capture_bitmap() {
    int x = GetSystemMetrics(SM_XVIRTUALSCREEN);
    int y = GetSystemMetrics(SM_YVIRTUALSCREEN);
    int w = GetSystemMetrics(SM_CXVIRTUALSCREEN);
    int h = GetSystemMetrics(SM_CYVIRTUALSCREEN);

    HDC screen = GetDC(nullptr);
    HDC mem = CreateCompatibleDC(screen);
    HBITMAP bmp = CreateCompatibleBitmap(screen, w, h);
    HGDIOBJ old = SelectObject(mem, bmp);
    BitBlt(mem, 0, 0, w, h, screen, x, y, SRCCOPY);
    SelectObject(mem, old);
    DeleteDC(mem);
    ReleaseDC(nullptr, screen);
    return bmp;
}

// encode HBITMAP → file; format: L"image/jpeg" or L"image/png"
bool save_bitmap(HBITMAP bmp, const std::wstring& path, const wchar_t* mime) {
    Gdiplus::Bitmap image(bmp, nullptr);
    CLSID clsid;
    if (mime == std::wstring(L"image/png"))
        CLSIDFromString(L"{557cf406-1a04-11d3-9a73-0000f81ef32e}", &clsid);
    else
        CLSIDFromString(L"{557cf401-1a04-11d3-9a73-0000f81ef32e}", &clsid);
    return image.Save(path.c_str(), &clsid, nullptr) == Gdiplus::Ok;
}

// ============ DXGI Desktop Duplication ============

struct DxgiCapture {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> ctx;
    ComPtr<IDXGIOutputDuplication> dupl;
    ComPtr<ID3D11Texture2D> staging;
    DXGI_OUTDUPL_DESC desc{};
    UINT width = 0, height = 0;

    bool init(int output_index = 0) {
        // pick adapter/output
        ComPtr<IDXGIFactory1> factory;
        if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory1), &factory)))
            return false;

        ComPtr<IDXGIAdapter1> adapter;
        ComPtr<IDXGIOutput> output;
        UINT ai = 0, oi = 0;
        bool found = false;
        while (factory->EnumAdapters1(ai, &adapter) != DXGI_ERROR_NOT_FOUND) {
            while (adapter->EnumOutputs(oi, &output) != DXGI_ERROR_NOT_FOUND) {
                if ((int)oi == output_index) { found = true; break; }
                output.Reset(); oi++;
            }
            if (found) break;
            adapter.Reset(); ai++; oi = 0;
        }
        if (!found) return false;

        ComPtr<IDXGIOutput1> output1;
        if (FAILED(output.As(&output1))) return false;

        D3D_FEATURE_LEVEL fl;
        if (FAILED(D3D11CreateDevice(adapter.Get(), D3D_DRIVER_TYPE_UNKNOWN,
                nullptr, 0, nullptr, 0, D3D11_SDK_VERSION,
                &device, &fl, &ctx)))
            return false;

        if (FAILED(output1->DuplicateOutput(device.Get(), &dupl)))
            return false;

        dupl->GetDesc(&desc);
        width = desc.ModeDesc.Width;
        height = desc.ModeDesc.Height;

        D3D11_TEXTURE2D_DESC td{};
        td.Width = width;
        td.Height = height;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = desc.ModeDesc.Format;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_STAGING;
        td.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        if (FAILED(device->CreateTexture2D(&td, nullptr, &staging)))
            return false;
        return true;
    }

    // grabs one frame into out_bgra (width*height*4); returns false on timeout
    bool grab(std::vector<BYTE>& out_bgra, UINT timeout_ms = 100) {
        DXGI_OUTDUPL_FRAME_INFO info{};
        ComPtr<IDXGIResource> res;
        HRESULT hr = dupl->AcquireNextFrame(timeout_ms, &info, &res);
        if (FAILED(hr)) return false;

        ComPtr<ID3D11Texture2D> tex;
        res.As(&tex);
        ctx->CopyResource(staging.Get(), tex.Get());

        D3D11_MAPPED_SUBRESOURCE map{};
        if (SUCCEEDED(ctx->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &map))) {
            out_bgra.resize(width * height * 4);
            for (UINT r = 0; r < height; r++) {
                memcpy(out_bgra.data() + r * width * 4,
                       (BYTE*)map.pData + r * map.RowPitch,
                       width * 4);
            }
            ctx->Unmap(staging.Get(), 0);
        }
        dupl->ReleaseFrame();
        return true;
    }

    // encode BGRA buffer to JPEG/PNG via GDI+
    bool save_frame(const std::vector<BYTE>& bgra, const std::wstring& path,
                    const wchar_t* mime) {
        Gdiplus::Bitmap bmp(width, height, width * 4, PixelFormat32bppARGB,
                            const_cast<BYTE*>(bgra.data()));
        CLSID clsid;
        if (mime == std::wstring(L"image/png"))
            CLSIDFromString(L"{557cf406-1a04-11d3-9a73-0000f81ef32e}", &clsid);
        else
            CLSIDFromString(L"{557cf401-1a04-11d3-9a73-0000f81ef32e}", &clsid);
        return bmp.Save(path.c_str(), &clsid, nullptr) == Gdiplus::Ok;
    }
};

// ============ main ============

int wmain(int argc, wchar_t** argv) {
    Gdiplus::GdiplusStartupInput gsi;
    ULONG_PTR gdip;
    Gdiplus::GdiplusStartup(&gdip, &gsi, nullptr);
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);

    // mode: gdi <out.jpg> | dxgi <out.jpg> | live <prefix> <count> <ms>
    std::wstring mode = argc > 1 ? argv[1] : L"gdi";

    if (mode == L"gdi") {
        HBITMAP bmp = gdi_capture_bitmap();
        std::wstring out = argc > 2 ? argv[2] : L"screen.jpg";
        save_bitmap(bmp, out, L"image/jpeg");
        DeleteObject(bmp);
        wprintf(L"[+] GDI capture → %s\n", out.c_str());
    }
    else if (mode == L"dxgi") {
        DxgiCapture cap;
        if (!cap.init(0)) { wprintf(L"[-] DXGI init failed\n"); return 1; }
        std::vector<BYTE> frame;
        if (cap.grab(frame)) {
            std::wstring out = argc > 2 ? argv[2] : L"screen_dxgi.jpg";
            cap.save_frame(frame, out, L"image/jpeg");
            wprintf(L"[+] DXGI capture %ux%u → %s\n", cap.width, cap.height,
                    out.c_str());
        }
    }
    else if (mode == L"live") {
        std::wstring prefix = argc > 2 ? argv[2] : L"frame_";
        int count = argc > 3 ? _wtoi(argv[3]) : 10;
        int ms    = argc > 4 ? _wtoi(argv[4]) : 500;
        DxgiCapture cap;
        if (!cap.init(0)) { wprintf(L"[-] DXGI init failed\n"); return 1; }
        std::vector<BYTE> frame;
        for (int i = 0; i < count; i++) {
            if (cap.grab(frame)) {
                wchar_t path[256];
                swprintf_s(path, L"%s%03d.jpg", prefix.c_str(), i);
                cap.save_frame(frame, path, L"image/jpeg");
                wprintf(L"[+] frame %d → %s\n", i, path);
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(ms));
        }
    }
    else {
        wprintf(L"usage:\n"
                L"  screencap gdi  <out.jpg>\n"
                L"  screencap dxgi <out.jpg>\n"
                L"  screencap live <prefix> <count> <interval_ms>\n");
    }

    CoUninitialize();
    Gdiplus::GdiplusShutdown(gdip);
    return 0;
}
