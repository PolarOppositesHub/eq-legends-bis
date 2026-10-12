/**
 * Frameless main window. The page draws the caption.
 * thickFrame stays on so Windows can snap and resize from the edges.
 * titleBarOverlay stays off so Windows does not paint a second set of buttons.
 * Double-click on the drag region is the native maximize toggle. The page
 * does not handle dblclick as well, or the window would toggle twice.
 */

function mainWindowChrome() {
  return {
    frame: false,
    thickFrame: true,
    titleBarOverlay: false,
    roundedCorners: true,
    backgroundColor: '#0a0a0a',
    autoHideMenuBar: true,
    closable: true,
    minimizable: true,
    maximizable: true,
    title: 'EQ Legends BiS',
  }
}

/** Electron call for a caption button. Close still goes through the window close handler. */
function windowControlCall(action, maximized) {
  if (action === 'minimize') return 'minimize'
  if (action === 'toggle-maximize') return maximized ? 'unmaximize' : 'maximize'
  if (action === 'close') return 'close'
  return ''
}

const TITLEBAR_DOUBLE_CLICK = 'native-drag-region'

module.exports = {
  TITLEBAR_DOUBLE_CLICK,
  mainWindowChrome,
  windowControlCall,
}
