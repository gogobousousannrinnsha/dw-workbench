"""Generated ctypes types from DocuWorks Development Tool Kit 9.1.7."""

import ctypes

class SYSTEMTIME(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ('wYear', ctypes.c_uint16), ('wMonth', ctypes.c_uint16),
        ('wDayOfWeek', ctypes.c_uint16), ('wDay', ctypes.c_uint16),
        ('wHour', ctypes.c_uint16), ('wMinute', ctypes.c_uint16),
        ('wSecond', ctypes.c_uint16), ('wMilliseconds', ctypes.c_uint16),
    ]

XDW_ANNOTATION_HANDLE = ctypes.c_void_p
XDW_CREATE_HANDLE = ctypes.c_void_p
XDW_DOCUMENT_HANDLE = ctypes.c_void_p
XDW_FOUND_HANDLE = ctypes.c_void_p

BOOL = ctypes.c_int32
XDW_WCHAR = ctypes.c_uint16

class XDW_RECT(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_GPTI_OCRTEXT_UNIT(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_GPTI_OCRTEXT(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_GPTI_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_DOCUMENT_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_PAGE_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_PAGE_INFO_EX(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_IMAGE_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OPEN_MODE(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OPEN_MODE_EX(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_CREATE_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_CREATE_OPTION_EX(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_CREATE_OPTION_EX2(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_ORGDATA_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_ORGDATA_INFOW(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_LINKROOTFOLDER_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_LINKROOTFOLDER_INFOW(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_CREATE_STATUS(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_ANNOTATION_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_FUSEN_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_STRAIGHTLINE_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_RECT_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_ARC_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_BITMAP_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_BITMAP_INITIAL_DATAW(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_STAMP_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_RECEIVEDSTAMP_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_CUSTOM_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_IMAGE_OPTION_EX(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_IMAGE_OPTION_TIFF(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_IMAGE_OPTION_JPEG(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_IMAGE_OPTION_PDF(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_BINDER_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_V4(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_V5(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_V5_EX(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_WRP(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_FRE(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_V7(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_FRE_V7(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_OPTION_V9(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_PAGE_COLOR_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SECURITY_OPTION_PSWD(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_DER_CERTIFICATE(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SECURITY_OPTION_PKI(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_PROTECT_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_RELEASE_PROTECTION_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_PROTECTION_INFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SIGNATURE_OPTION_V5(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SIGNATURE_INFO_V5(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SIGNATURE_MODULE_STATUS(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SIGNATURE_MODULE_OPTION_PKI(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SIGNATURE_STAMP_INFO_V5(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_SIGNATURE_PKI_INFO_V5(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCR_TEXTINFO(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_OCRIMAGE_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_FIND_TEXT_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_POINT(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_MARKER_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_AA_POLYGON_INITIAL_DATA(ctypes.Structure):
    _pack_ = 8
    pass

class XDW_BEGIN_CREATE_OPTION(ctypes.Structure):
    _pack_ = 8
    pass

XDW_RECT._fields_ = [
    ('left', ctypes.c_int32),
    ('top', ctypes.c_int32),
    ('right', ctypes.c_int32),
    ('bottom', ctypes.c_int32),
]

XDW_GPTI_OCRTEXT_UNIT._fields_ = [
    ('lpszText', ctypes.c_char_p),
    ('rect', XDW_RECT),
]

XDW_GPTI_OCRTEXT._fields_ = [
    ('nUnitNum', ctypes.c_int32),
    ('pUnits', ctypes.POINTER(XDW_GPTI_OCRTEXT_UNIT)),
]

XDW_GPTI_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nInfoType', ctypes.c_int32),
    ('nPageWidth', ctypes.c_int32),
    ('nPageHeight', ctypes.c_int32),
    ('nRotateDegree', ctypes.c_int32),
    ('nDataSize', ctypes.c_int32),
    ('pData', ctypes.c_void_p),
]

XDW_DOCUMENT_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nPages', ctypes.c_int32),
    ('nVersion', ctypes.c_int32),
    ('nOriginalData', ctypes.c_int32),
    ('nDocType', ctypes.c_int32),
    ('nPermission', ctypes.c_int32),
    ('nShowAnnotations', ctypes.c_int32),
    ('nDocuments', ctypes.c_int32),
    ('nBinderColor', ctypes.c_int32),
    ('nBinderSize', ctypes.c_int32),
]

XDW_PAGE_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nPageType', ctypes.c_int32),
    ('nHorRes', ctypes.c_int32),
    ('nVerRes', ctypes.c_int32),
    ('nCompressType', ctypes.c_int32),
    ('nAnnotations', ctypes.c_int32),
]

XDW_PAGE_INFO_EX._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nPageType', ctypes.c_int32),
    ('nHorRes', ctypes.c_int32),
    ('nVerRes', ctypes.c_int32),
    ('nCompressType', ctypes.c_int32),
    ('nAnnotations', ctypes.c_int32),
    ('nDegree', ctypes.c_int32),
    ('nOrgWidth', ctypes.c_int32),
    ('nOrgHeight', ctypes.c_int32),
    ('nOrgHorRes', ctypes.c_int32),
    ('nOrgVerRes', ctypes.c_int32),
    ('nImageWidth', ctypes.c_int32),
    ('nImageHeight', ctypes.c_int32),
]

XDW_IMAGE_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nDpi', ctypes.c_int32),
    ('nColor', ctypes.c_int32),
]

XDW_OPEN_MODE._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nOption', ctypes.c_int32),
]

XDW_OPEN_MODE_EX._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nOption', ctypes.c_int32),
    ('nAuthMode', ctypes.c_int32),
]

XDW_CREATE_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nFitImage', ctypes.c_int32),
    ('nCompress', ctypes.c_int32),
    ('nZoom', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nHorPos', ctypes.c_int32),
    ('nVerPos', ctypes.c_int32),
]

XDW_CREATE_OPTION_EX._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nFitImage', ctypes.c_int32),
    ('nCompress', ctypes.c_int32),
    ('nZoom', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nHorPos', ctypes.c_int32),
    ('nVerPos', ctypes.c_int32),
    ('nZoomDetail', ctypes.c_int32),
]

XDW_CREATE_OPTION_EX2._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nFitImage', ctypes.c_int32),
    ('nCompress', ctypes.c_int32),
    ('nZoom', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nHorPos', ctypes.c_int32),
    ('nVerPos', ctypes.c_int32),
    ('nZoomDetail', ctypes.c_int32),
    ('nMaxPaperSize', ctypes.c_int32),
]

XDW_ORGDATA_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nDataSize', ctypes.c_int32),
    ('nDate', ctypes.c_int32),
    ('szName', ctypes.c_char * 256),
]

XDW_ORGDATA_INFOW._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nDataSize', ctypes.c_int32),
    ('nDate', ctypes.c_int32),
    ('szName', XDW_WCHAR * 256),
]

XDW_LINKROOTFOLDER_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('szPath', ctypes.c_char * 256),
    ('szLinkRootFolderName', ctypes.c_char * 256),
]

XDW_LINKROOTFOLDER_INFOW._fields_ = [
    ('nSize', ctypes.c_int32),
    ('wszPath', XDW_WCHAR * 256),
    ('wszLinkRootFolderName', XDW_WCHAR * 256),
]

XDW_CREATE_STATUS._fields_ = [
    ('nSize', ctypes.c_int32),
    ('phase', ctypes.c_int32),
    ('nTotalPage', ctypes.c_int32),
    ('nPage', ctypes.c_int32),
]

XDW_ANNOTATION_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('handle', XDW_ANNOTATION_HANDLE),
    ('nHorPos', ctypes.c_int32),
    ('nVerPos', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nAnnotationType', ctypes.c_int32),
    ('nChildAnnotations', ctypes.c_int32),
]

XDW_AA_INITIAL_DATA._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nAnnotationType', ctypes.c_int32),
    ('nReserved1', ctypes.c_int32),
    ('nReserved2', ctypes.c_int32),
]

XDW_AA_FUSEN_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
]

XDW_AA_STRAIGHTLINE_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nHorVec', ctypes.c_int32),
    ('nVerVec', ctypes.c_int32),
]

XDW_AA_RECT_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
]

XDW_AA_ARC_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
]

XDW_AA_BITMAP_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('szImagePath', ctypes.c_char * 256),
]

XDW_AA_BITMAP_INITIAL_DATAW._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('wszImagePath', XDW_WCHAR * 256),
]

XDW_AA_STAMP_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nWidth', ctypes.c_int32),
]

XDW_AA_RECEIVEDSTAMP_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nWidth', ctypes.c_int32),
]

XDW_AA_CUSTOM_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('lpszGuid', ctypes.c_char_p),
    ('nCustomDataSize', ctypes.c_int32),
    ('pCustomData', ctypes.POINTER(ctypes.c_ubyte)),
]

XDW_IMAGE_OPTION_EX._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nDpi', ctypes.c_int32),
    ('nColor', ctypes.c_int32),
    ('nImageType', ctypes.c_int32),
    ('pDetailOption', ctypes.c_void_p),
]

XDW_IMAGE_OPTION_TIFF._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nCompress', ctypes.c_int32),
    ('nEndOfMultiPages', ctypes.c_int32),
]

XDW_IMAGE_OPTION_JPEG._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nCompress', ctypes.c_int32),
]

XDW_IMAGE_OPTION_PDF._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nCompress', ctypes.c_int32),
    ('nConvertMethod', ctypes.c_int32),
    ('nEndOfMultiPages', ctypes.c_int32),
]

XDW_BINDER_INITIAL_DATA._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nBinderColor', ctypes.c_int32),
    ('nBinderSize', ctypes.c_int32),
]

XDW_OCR_OPTION_V4._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nInsertSpaceCharacter', ctypes.c_int32),
    ('nJapaneseKnowledgeProcessing', ctypes.c_int32),
    ('nForm', ctypes.c_int32),
    ('nColumn', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
]

XDW_OCR_OPTION_V5._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nInsertSpaceCharacter', ctypes.c_int32),
    ('nJapaneseKnowledgeProcessing', ctypes.c_int32),
    ('nForm', ctypes.c_int32),
    ('nColumn', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nAreaNum', ctypes.c_uint32),
    ('pAreaRects', ctypes.POINTER(ctypes.POINTER(XDW_RECT))),
]

XDW_OCR_OPTION_V5_EX._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nInsertSpaceCharacter', ctypes.c_int32),
    ('nJapaneseKnowledgeProcessing', ctypes.c_int32),
    ('nForm', ctypes.c_int32),
    ('nColumn', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nAreaNum', ctypes.c_uint32),
    ('pAreaRects', ctypes.POINTER(ctypes.POINTER(XDW_RECT))),
    ('nPriority', ctypes.c_int32),
]

XDW_OCR_OPTION_WRP._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nInsertSpaceCharacter', ctypes.c_int32),
    ('nForm', ctypes.c_int32),
    ('nColumn', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nPriority', ctypes.c_int32),
]

XDW_OCR_OPTION_FRE._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nDocumentType', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nAreaNum', ctypes.c_uint32),
    ('pAreaRects', ctypes.POINTER(ctypes.POINTER(XDW_RECT))),
    ('nPriority', ctypes.c_int32),
]

XDW_OCR_OPTION_V7._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nInsertSpaceCharacter', ctypes.c_int32),
    ('nJapaneseKnowledgeProcessing', ctypes.c_int32),
    ('nForm', ctypes.c_int32),
    ('nColumn', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nAreaNum', ctypes.c_uint32),
    ('pAreaRects', ctypes.POINTER(ctypes.POINTER(XDW_RECT))),
    ('nPriority', ctypes.c_int32),
    ('nEngineLevel', ctypes.c_int32),
    ('nLanguageMixedRate', ctypes.c_int32),
    ('nHalfSizeChar', ctypes.c_int32),
]

XDW_OCR_OPTION_FRE_V7._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nDocumentType', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nAreaNum', ctypes.c_uint32),
    ('pAreaRects', ctypes.POINTER(ctypes.POINTER(XDW_RECT))),
    ('nPriority', ctypes.c_int32),
    ('nEngineLevel', ctypes.c_int32),
]

XDW_OCR_OPTION_V9._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nLanguage', ctypes.c_int32),
    ('nInsertSpaceCharacter', ctypes.c_int32),
    ('nForm', ctypes.c_int32),
    ('nColumn', ctypes.c_int32),
    ('nDisplayProcess', ctypes.c_int32),
    ('nAutoDeskew', ctypes.c_int32),
    ('nAreaNum', ctypes.c_uint32),
    ('pAreaRects', ctypes.POINTER(ctypes.POINTER(XDW_RECT))),
    ('nPriority', ctypes.c_int32),
    ('nEngineLevel', ctypes.c_int32),
    ('nHalfSizeChar', ctypes.c_int32),
]

XDW_PAGE_COLOR_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nColor', ctypes.c_int32),
    ('nImageDepth', ctypes.c_int32),
]

XDW_SECURITY_OPTION_PSWD._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nPermission', ctypes.c_int32),
    ('szOpenPswd', ctypes.c_char * 256),
    ('szFullAccessPswd', ctypes.c_char * 256),
    ('lpszComment', ctypes.c_char_p),
]

XDW_DER_CERTIFICATE._fields_ = [
    ('pCert', ctypes.c_void_p),
    ('nCertSize', ctypes.c_int32),
]

XDW_SECURITY_OPTION_PKI._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nPermission', ctypes.c_int32),
    ('lpxdcCerts', ctypes.POINTER(XDW_DER_CERTIFICATE)),
    ('nCertsNum', ctypes.c_int32),
    ('nFullAccessCertsNum', ctypes.c_int32),
    ('nErrorStatus', ctypes.c_int32),
    ('nFirstErrorCert', ctypes.c_int32),
]

XDW_PROTECT_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nAuthMode', ctypes.c_int32),
]

XDW_RELEASE_PROTECTION_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nAuthMode', ctypes.c_int32),
]

XDW_PROTECTION_INFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nProtectType', ctypes.c_int32),
    ('nPermission', ctypes.c_int32),
]

XDW_SIGNATURE_OPTION_V5._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nPage', ctypes.c_int32),
    ('nHorPos', ctypes.c_int32),
    ('nVerPos', ctypes.c_int32),
    ('nSignatureType', ctypes.c_int32),
]

XDW_SIGNATURE_INFO_V5._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nSignatureType', ctypes.c_int32),
    ('nPage', ctypes.c_int32),
    ('nHorPos', ctypes.c_int32),
    ('nVerPos', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('nSignedTime', ctypes.c_int32),
]

XDW_SIGNATURE_MODULE_STATUS._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nSignatureType', ctypes.c_int32),
    ('nErrorStatus', ctypes.c_int32),
]

XDW_SIGNATURE_MODULE_OPTION_PKI._fields_ = [
    ('nSize', ctypes.c_int32),
    ('pSignerCert', ctypes.c_void_p),
    ('nSignerCertSize', ctypes.c_int32),
]

XDW_SIGNATURE_STAMP_INFO_V5._fields_ = [
    ('nSize', ctypes.c_int32),
    ('lpszStampName', ctypes.c_char * 256),
    ('lpszOwnerName', ctypes.c_char * 64),
    ('nValidDate', ctypes.c_int32),
    ('lpszRemarks', ctypes.c_char * 1024),
    ('nDocVerificationStatus', ctypes.c_int32),
    ('nStampVerificationStatus', ctypes.c_int32),
]

XDW_SIGNATURE_PKI_INFO_V5._fields_ = [
    ('nSize', ctypes.c_int32),
    ('lpszModule', ctypes.c_char * 16),
    ('lpszSubjectDN', ctypes.c_char * 512),
    ('lpszSubject', ctypes.c_char * 256),
    ('lpszIssuerDN', ctypes.c_char * 512),
    ('lpszIssuer', ctypes.c_char * 256),
    ('lpszNotBefore', ctypes.c_char * 32),
    ('lpszNotAfter', ctypes.c_char * 32),
    ('lpszSerial', ctypes.c_char * 64),
    ('pSignerCert', ctypes.c_void_p),
    ('nSignerCertSize', ctypes.c_int32),
    ('lpszRemarks', ctypes.c_char * 64),
    ('lpszSigningTime', ctypes.c_char * 32),
    ('nDocVerificationStatus', ctypes.c_int32),
    ('nCertVerificationType', ctypes.c_int32),
    ('nCertVerificationStatus', ctypes.c_int32),
]

XDW_OCR_TEXTINFO._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nWidth', ctypes.c_int32),
    ('nHeight', ctypes.c_int32),
    ('charset', ctypes.c_int32),
    ('lpszText', ctypes.c_char_p),
    ('nLineRect', ctypes.c_int32),
    ('pLineRect', ctypes.POINTER(XDW_RECT)),
]

XDW_OCRIMAGE_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nDpi', ctypes.c_int32),
    ('nNoiseReduction', ctypes.c_int32),
    ('nPriority', ctypes.c_int32),
]

XDW_FIND_TEXT_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('nIgnoreMode', ctypes.c_int32),
    ('nReserved', ctypes.c_int32),
    ('nReserved2', ctypes.c_int32),
]

XDW_POINT._fields_ = [
    ('x', ctypes.c_int32),
    ('y', ctypes.c_int32),
]

XDW_AA_MARKER_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nCounts', ctypes.c_int32),
    ('pPoints', ctypes.POINTER(XDW_POINT)),
]

XDW_AA_POLYGON_INITIAL_DATA._fields_ = [
    ('common', XDW_AA_INITIAL_DATA),
    ('nCounts', ctypes.c_int32),
    ('pPoints', ctypes.POINTER(XDW_POINT)),
]

XDW_BEGIN_CREATE_OPTION._fields_ = [
    ('nSize', ctypes.c_int32),
    ('bNoUseSpecifiedApp', ctypes.c_int32),
]

TYPEDEF_STRUCT_COUNT = 66
STRUCTURE_CLASS_COUNT = 62
