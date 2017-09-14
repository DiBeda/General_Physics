#coding=utf-8

import Tkinter, tkFileDialog, ttk, tkMessageBox
import time 
from numpy import * 
from numpy import round, max 
from PIL import Image, ImageTk, ImageDraw


#CONSTANTS---------------------------------------------------------------------
mu0      = 1.2566370614e-6	
epsilon0 = 8.854187817620e-12	
c        = 1/(mu0*epsilon0)**0.5


canvasX = 900 #width of view canvas
canvasY = 280 #height of view canvas
barrierX = 50	#x position of the barrier
pmlWidth = 16 #width of the perfectly matched layer, not including the PEC boundary

Nx = canvasX - barrierX + pmlWidth + 1	#width of the FDTD domain; overlaps anayltic domain by one and has PML + PEC on right side
Ny = canvasY + 2*pmlWidth + 2		#height of the FDTD domain; has PML and PEC on top and bottom
  
plotD = 100	#free dimension of 1D plots
  
d  = 2.0/(canvasX-1)	#spatial grid element size
dt = d/c/2**0.5	#time step -- this choice is good for a 2D simulation in vacuum, will modify shortly

#the wave:
lamb  = 5*d		#wavelength -- 20 points per wavelength yeilds good results
k     = 2*pi/lamb	#wavenumber
omega = 2*pi*c/lamb	#angular frequency
tau   = lamb/c		#time period

dt = tau/ceil(tau/dt) #now, modify dt so that tau is an integer number of timesteps; this formulation makes dt less than or equal to its previous value, which is nescessary for stability

#stability time step counts
nStable = int((barrierX + sqrt((canvasX-barrierX)**2 + canvasY**2))*d/c/dt) #time steps until Ez becomes stable: to barrier then longest way across right domain
nAvgStable = int(round(tau/dt)) #average for one cycle (once Ez is already stable)
 
NEZx = Nx #number of Ez grid points in x direction -- goes all the way to the edge
NEZy = Ny #number of Ez grid points in y direction -- goes all the way to the edge
#range updated by Yee algorithm:
EZx_range = slice(1, NEZx-1) #right and left are PECs, so not updated using Yee algorithm
EZy_range = slice(1, NEZy-1) #top and bottom are PECs, so not updated using Yee algorithm
#range that's visible
EZx_vis_range = slice(0, -(pmlWidth+1))
EZy_vis_range = slice((pmlWidth+1), -(pmlWidth+1))
#range updated by analyitic formula:
EZx_an_range = slice(0, barrierX+1)
EZy_an_range = slice(0, canvasY) #only make as tall as the canvas
#all of the visible range
EZx_all = slice(0,canvasX)
EZy_all = slice(0,canvasY)
  
NHXx = Nx     #Hx goes all the way to x endpoints
NHXy = Ny - 1 #Hx not at y endpoints, so -1
HXx_range = slice(0, NHXx) #all positions updated using Yee
HXy_range = slice(0, NHXy)

NHYx = Nx - 1 #Hy not at x endpoints, so -1
NHYy = Ny     #Hy goes all the way to y endpoints
HYx_range = slice(0, NHYx) #all y positions updated using Yee
HYy_range = slice(0, NHYy)

#зададим электрическую и магнитную пронициаемость
m   = 3	    
ref = 1e-9	#коэффициент отражения
eta = sqrt(mu0/epsilon0)
wd   = pmlWidth*d	
sigmaMax   = -(m+1)*log(ref)/2/eta/wd
sigmaStMax = mu0/epsilon0*sigmaMax

sigmas   = sigmaMax*((arange(pmlWidth) + 0.0)/(pmlWidth))**m
sigmaSts = sigmaStMax*((arange(pmlWidth) + 0.5)/(pmlWidth))**m

#проницаемости
sigmaStX = zeros((NHYx,NHYy)) #для обновления Hy
sigmaStX[-pmlWidth:,:] = sigmaSts[:, newaxis]

sigmaStY = zeros((NHXx,NHXy)) #для обновления Hx
sigmaStY[:,:pmlWidth] = sigmaSts[::-1]
sigmaStY[:,-pmlWidth:] = sigmaSts

sigmaX = zeros((NEZx-2,NEZy-2)) #для обновления Ezx в EZx_range и EZy_range, -2 потому что не обновляем для PEC
sigmaX[-pmlWidth:] = sigmas[:, newaxis]

sigmaY = zeros((NEZx-2,NEZy-2)) #для обновления Ezx в EZx_range и EZy_range, -2 потому что не обновляем для PEC
sigmaY[:,-pmlWidth:] = sigmas
sigmaY[:,:pmlWidth] = sigmas[::-1] 

#Коэффициенты алгоритма Йи для обновления
CaX = (1-sigmaX*dt/2/epsilon0)/(1+sigmaX*dt/2/epsilon0)
CaY = (1-sigmaY*dt/2/epsilon0)/(1+sigmaY*dt/2/epsilon0)
CbX = dt/epsilon0/d/(1+sigmaX*dt/2/epsilon0)
CbY = dt/epsilon0/d/(1+sigmaY*dt/2/epsilon0)

DaX = (1-sigmaStX*dt/2/mu0)/(1+sigmaStX*dt/2/mu0)
DaY = (1-sigmaStY*dt/2/mu0)/(1+sigmaStY*dt/2/mu0)
DbX = dt/mu0/d/(1+sigmaStX*dt/2/mu0)
DbY = dt/mu0/d/(1+sigmaStY*dt/2/mu0)

#ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ------------------------------------------------------

#шаги по времени
n          = 0 #номер нынешнего шага
nAveraging = 0 
nCount     = nStable #время, через которое будет стабильное состояние

#booleans
running        = False #stores whether or not the simulation is currently running
fastForwarding = False #stores whether or not the simulation is in fast forward mode (where it saves time by not updating the plots)

#numpy arrays
#for FDTD domain
Ez       = zeros((NEZx, NEZy))
Ezx      = zeros((NEZx, NEZy))
Ezy      = zeros((NEZx, NEZy))
Hx       = zeros((NHXx, NHXy))
Hy       = zeros((NHYx, NHYy))
#for whole visible domain
EzSQsum = zeros((canvasX, canvasY)) #sum of 'Ez^2's at each timestep we've averaged over
EzRMSSQ = zeros((canvasX, canvasY)) #Ez_RMS^2
EzRMS   = zeros((canvasX, canvasY)) #Ez_RMS
#for the anayltic domain
EzAn	= zeros((barrierX+1, canvasY))
#for the visible domain
EzVis = zeros((canvasX,canvasY))

#largest array elements
maxEz    = 1 #contains the largest Ez seen >=1
maxEzRMS = 1 #contains the largest Ez_RMS seen -- start it at one to avoid divide by zero problems on the first canvas refresh


#THE METHODS-------------------------------------------------------------------
def barrierChanged():
  """Any time the barrier gets changed, we need to wait for stability again, so maxEz and nCount are changed."""
  global nCount
  global maxEz
  
  maxEz = 1
  nCount = n + nStable
  root.focus() #removes focus from whatever spinbox it was on, so that it doesn't steal arrow key presses and the likes
  conditionalRedraw()
      
def addOpening():
  """Adds the opening described by bottomEntry and topEntry, if it's in range and doesn't overlap with exsisting gaps"""
  global gaps
  
  bot = int(bottomEntry.get())	#top of proposed opening
  top = int(topEntry.get())	#bottom of proposed opening
  if bot > 0 and top < canvasY and bot < top: #some initial checks that top and bot better pass
    newOrder = gaps[:] #copy gaps, don't just point to it
    newOrder.append([bot,top])
    newOrder.sort() #sorts by first entry of each pair (the bottom)
    newOrderFlat = [ypos for pair in newOrder for ypos in pair] #flatten
    if (newOrderFlat == sorted(newOrderFlat) #catches things like [50,100],[90,120] -- overlapping openings
      and len(list(set(newOrderFlat))) == len(newOrderFlat)): #catchs things like [50,100],[100,120] -- openings with no space between them
      gaps = newOrder
      redrawBarrierFrame()
      barrierChanged()
  
def redrawBarrierFrame():
  """Each opening gets its own frame withing the barrier frame. This method redraws those."""
  global barrierFrames
  global intVars
  global distStrVars
  global updateButtons
  global spinboxes
  
  gaps.sort()
  for f in barrierFrames:
    f.destroy() #get rid of old frames
  barrierFrames = []
  updateButtons = [] #holds the buttons for updating the openings
  spinboxes     = [] #holds the spinboxes for entering the top and bottom positions of the openings
  intVars       = [] #need to save StringVars or else they get garbage collected
  distStrVars   = [] #holds stringVars that report the distance from the center of the gaps to the slice intersection
  r = 3 #rows 0,1,2 already taken by widgets for adding an opeing
    
  for gap in gaps:
    oNum = r-3 #opening number
    frame = ttk.Labelframe(barrierFrame, text="Щель {}".format(oNum))
    frame.grid(column=0, row=r, columnspan=2, sticky='nesw', padx=5, pady=5)
      
    top = Tkinter.IntVar()
    bottom = Tkinter.IntVar()
    distStrVar = Tkinter.StringVar()
    
    #the spinbox for the bottom of the opening
    ttk.Label(frame, text="Нижнее значение:").grid(column=0, row=0, sticky='nes', padx=5, pady=5)
    spinbox = Tkinter.Spinbox(frame, width=4, textvariable=bottom, from_=0, to=canvasX, command=lambda n=oNum: spinboxChanged(n))
    spinbox.bind("<KeyRelease>",lambda arg, n=oNum: spinboxChanged(n)) #any key runs the spinboxChanged method, which will enable or disable the 'update' button
    spinbox.grid(column=1, row=0, sticky='nsw', padx=5, pady=5)
    spinboxes.append(spinbox)
    
    #the spinbox for the top of the opening
    ttk.Label(frame, text="Верхнее значение:").grid(column=0, row=1, sticky='nes', padx=5, pady=5)
    spinbox = Tkinter.Spinbox(frame, width=4, textvariable=top, from_=0, to=canvasX, command=lambda n=oNum: spinboxChanged(n))
    spinbox.bind("<KeyRelease>",lambda arg, n=oNum: spinboxChanged(n))
    spinbox.grid(column=1, row=1, sticky='nsw', padx=5, pady=5)
    ttk.Label(frame, textvariable=distStrVar).grid(column=0, row=2, sticky='nes', padx=5, pady=5)
    spinboxes.append(spinbox)
    
    ub = ttk.Button(frame, text='Обновить значения', state="disabled", command=lambda n=oNum: updateOpening(n))
    ub.grid(column=0, row=3, sticky='nsew', columnspan=2, padx=5, pady=5)
    updateButtons.append(ub)
    ttk.Button(frame, text='Убрать', command=lambda n=oNum: removeOpening(n)).grid(column=0, row=4, sticky='nsew', columnspan=2, padx=5, pady=5)
    top.set(gap[1])
    bottom.set(gap[0])
    intVars.append(top)
    intVars.append(bottom) 
    distStrVars.append(distStrVar)
      
    barrierFrames.append(frame)
    r += 1
  updateDistStrVars()

def spinboxChanged(openingNumber):
  """Called any time a spinbox for an opening top or bottom is changed. This enables or disables the 'update' button."""
  try:
    if goodOpeningBot(openingNumber):
      spinboxes[openingNumber*2].config(foreground="black")
    else:
      spinboxes[openingNumber*2].config(foreground="red")
      
    if goodOpeningTop(openingNumber):
      spinboxes[openingNumber*2+1].config(foreground="black")
    else:
      spinboxes[openingNumber*2+1].config(foreground="red")
      
    currentTop = intVars[openingNumber*2].get()
    currentBot = intVars[openingNumber*2+1].get()
    if ((gaps[openingNumber][1] != currentTop) or (gaps[openingNumber][0] != currentBot)) and goodOpeningBot(openingNumber) and goodOpeningTop(openingNumber): #if either the top or bottom spibox value is different from the stored values and the positions are good, enable the update button
      updateButtons[openingNumber].config(state="normal")
    else: #if neither are different, then disable the button
      updateButtons[openingNumber].config(state="disabled")
  except ValueError: #one of the entered strings isn't a valid number
    updateButtons[openingNumber].config(state="disabled")

def goodOpeningTop(openingNumber):
  """Returns true if the top of the opening is in a good position, and false if it's not."""
  try: #if the text in the spinbox isn't a number, we'll get an exception
    value  = intVars[openingNumber*2].get()
    bottom = intVars[openingNumber*2+1].get()
  except:
    return False
    
  if ((openingNumber == (len(gaps)-1)) and (value < canvasY) and (value > bottom)) or ((openingNumber < (len(gaps)-1)) and (value < gaps[openingNumber+1][0]) and (value > bottom)):
    return True
  else:
    return False

def goodOpeningBot(openingNumber):
  """Returns true if the bottom of the opening is in a good position, and false if it's not."""
  try: #if the text in the spinbox isn't a number, we'll get an exception
    value = intVars[openingNumber*2+1].get()
    top   = intVars[openingNumber*2].get()
  except:
    return False
    
  if ((openingNumber == 0) and (value > 0) and (value < top)) or ((openingNumber > 0) and (value > gaps[openingNumber-1][1]) and (value < top)):
    return True
  else:
    return False    
    
def updateOpening(openingNumber):
  """Updates the opening if the new values are alright"""
  global gaps

  try:
    top = intVars[openingNumber*2].get()
    bot = intVars[openingNumber*2+1].get()
    if ((gaps[openingNumber][1] != top) or (gaps[openingNumber][0] != bot)) and goodOpeningTop(openingNumber) and goodOpeningBot(openingNumber): #don't do anything if nothing has changed or if the opening is bad
      gaps[openingNumber][1] = top
      gaps[openingNumber][0] = bot
      barrierChanged()
  except:
    pass

  spinboxChanged(openingNumber) #regaurdless of what happened, the update box should be disabled
  
def updateDistStrVars():
  """Updates all the StringVars in distStrVars to hold the correct distance from the gap to the slice intersection"""
  for gap, tv in zip(gaps, distStrVars):
    tv.set("r = " + str(int(round(sqrt(((gap[0]+gap[1])/2.0-sliceY)**2+(barrierX-sliceX)**2)))) + "d")
  
def removeOpening(openingNumber):
  """Gets rid of the opening number openingNumber"""
  global gaps

  del gaps[openingNumber]
  redrawBarrierFrame()
  barrierChanged()
    
def clearCanvasBindings(eventObj):
  """Removes the command bound to dragging the mouse on the canvas, used after the mouse button has been released when dragging is done"""
  Ezcanvas.bind("<B1-Motion>", lambda e: None)
  HorizPlotCanvas.bind("<B1-Motion>", lambda e: None)
  EzRMScanvas.bind("<B1-Motion>", lambda e: None)
  VertPlotCanvas1.bind("<B1-Motion>", lambda e: None)
  VertPlotCanvas2.bind("<B1-Motion>", lambda e: None)

def invertedGaps():
  """Returns [0, start of first gap, end of first gap, start of second gap, end of second gap,...,canvasY]"""
  invGaps = [ypos for pair in gaps for ypos in pair] #flatten gaps
  invGaps.insert(0,0) #insert zero at the 0th position
  invGaps.append(canvasY) #put canvasY for the last item
  return invGaps  
  
def updateEzPlot():
  """Makes a plot of Ez and stores it in ezPlot"""
  global ezPlot
  #notes:
  #1)Image.frombytes can only handle 32bit floats, so need to do that conversion
  #2)0 (and below) are black, 255 and above are white, shades of gray inbetween
  #3)need to store array in (height, width) format
  data = float32((transpose(EzVis[:,:])/maxEz + 1)/2*256) #+1 so that zero is in the center
  im = Image.frombytes('F', (data.shape[1], data.shape[0]), data.tostring())
  ezPlot = ImageTk.PhotoImage(image=im) #need to store it so it doesn't get garbage collected, otherwise it won't display correctly on the canvas
    
def updateEzRMSPlot():
  """Makes a plot of Ez_RMS or Ez_RMS^2 (whichever is selected by the user) and stores it in ezRMSPlot"""
  global ezRMSPlot
  
  if avgSetting.get() == 'sq': #want to display Ez_RMS^2
    data = 256*(float32(transpose(EzRMSSQ)/maxEzRMS**2))  
  else: #want to display Ez_RMS
    data = 256*(float32(transpose(EzRMS/maxEzRMS)))    
  im = Image.frombytes('F', (data.shape[1], data.shape[0]), data.tostring())
  ezRMSPlot = ImageTk.PhotoImage(image=im) #need to store it so it doesn't get garbage collected, otherwise it won't display correctly on the canvas

def makeAvgedTrace(xS, yS, invert=False, othercoord=None):
  """Stores the appropriate x or y values for the small canvas for the given x and y slices for the averaged traces (amplitude, Ez_RMS, or Ez_RMS^2).
  Values are flipped across the long axis of the canvas if inverTrue.
  If othercoord is an array (e.g. it's the x values we're finding the y values at),
  then its reverse is appended to itself so that it's like [0,1...,canvasX-1,canvasX,canvasX,canvasX-1,...,1,0],
  and the y values are similiarly stored like [V0,...,Vn,-Vn,...,-V0], so that we plot +/- of the value"""
  if avgSetting.get() == 'amp': #want to display amplitude = EzRMS*sqrt(2) with zero in middle of plot
    v = int_(round((1+(EzRMS[xS,yS]*sqrt(2))/maxEz)*(plotD/2)))
    if othercoord != None: #in this case, let's plot +/-amplitude, not just amplitude
      othercoord.extend(othercoord[::-1]) #extend the coordinates so they're like [0,1...,canvasX-1,canvasX,canvasX,canvasX-1,...,1,0]
      v = concatenate((v,plotD-v[::-1])) #extend the values so they're like [V0,...,Vn,-Vn,...,-V0]
  elif avgSetting.get() == 'rms': #want to display EzRMS with zero at bottom of plot
    v = int_(round((EzRMS[xS,yS]/maxEzRMS)*(plotD-1)))
  else: #want to display EzRMS^2 with zero at bottom of plot
    v = int_(round((EzRMSSQ[xS,yS]/maxEzRMS**2)*(plotD-1)))
    
  if invert: #mirror results across axis
    v = plotD - v
  return v
    
def plot(draw, x, y, color):
  """Plots the 1D data on the drawing in the given color"""
  if traceSetting.get() == 'line': #line plot
    draw.line(zip(x,y), fill=color)
  else: #dot plot
    draw.point(zip(x,y), fill=color)
      
def updateHorizPlot():
  """Updates the horizontal 1D plot"""
  global horizPlot
  
  im = Image.new('RGB', (canvasX,plotD))
  draw = ImageDraw.Draw(im)
  x = range(0,canvasX)
  #plot EzRMS
  y = makeAvgedTrace(EZx_all, sliceY, invert=True, othercoord=x)
  plot(draw, x, y, 'green')
  #plot EzVis
  y = int_(round((-EzVis[:,sliceY]/maxEz+1)*(plotD/2)))
  plot(draw, x, y, 'yellow')
  #turn plot in to a format the canvas can use
  horizPlot = ImageTk.PhotoImage(image=im)

def updateVertPlot():
  """Updates the vertical 1D plot"""
  global vertPlot
  
  im = Image.new('RGB', (plotD, canvasY))
  draw = ImageDraw.Draw(im)
  y = range(0,canvasY)
  #plot EzRMS
  x = makeAvgedTrace(sliceX, EZy_all, othercoord=y)
  plot(draw, x, y, 'green')
  #plot EzVis
  x = int_(round((EzVis[sliceX,:]/maxEz+1)*(plotD/2)))
  plot(draw, x, y, 'yellow')
  #turn plot in to a format the canvas can use  
  vertPlot = ImageTk.PhotoImage(image=im)  
    
def redrawCanvases():
  """Updates and redraws all the canvases as well as update the time step, EzVis, and Ez_RMS labels"""
  #first, clear everything off the canvases (but don't delete the canvases themselves)
  Ezcanvas.delete('all')
  HorizPlotCanvas.delete('all')
  EzRMScanvas.delete('all')
  VertPlotCanvas1.delete('all')
  VertPlotCanvas2.delete('all')
  
  #now, put the plots on the canvases
  updateEzPlot()
  Ezcanvas.create_image(0,0,image=ezPlot,anchor=Tkinter.NW)
  updateHorizPlot()
  HorizPlotCanvas.create_image(0,0,image=horizPlot,anchor=Tkinter.NW)  
  updateEzRMSPlot()
  EzRMScanvas.create_image(0,0,image=ezRMSPlot,anchor=Tkinter.NW)
  HorizPlotCanvas.create_image(0,0,image=horizPlot,anchor=Tkinter.NW)  
  updateVertPlot()
  VertPlotCanvas1.create_image(0,0,image=vertPlot,anchor=Tkinter.NW)  
  VertPlotCanvas2.create_image(0,0,image=vertPlot,anchor=Tkinter.NW)  
  
  #next, draw the barrier
  invGaps = invertedGaps()
  for i in range(0,len(invGaps),2):
    Ezcanvas.create_line([(barrierX,invGaps[i]),(barrierX,invGaps[i+1])], width=1, fill='red')    
    EzRMScanvas.create_line([(barrierX,invGaps[i]),(barrierX,invGaps[i+1])], width=1, fill='red')
  
  #draw lines from the center of the gaps to the slice intersection, if desired
  if distLineSetting.get() == "lines":
    for gap, distStrVar in zip(gaps,distStrVars):
      #draw the lines
      yGap = (gap[0]+gap[1])/2
      Ezcanvas.create_line([(barrierX,yGap),(sliceX,sliceY)], width=1, fill='orange', dash=',')
      EzRMScanvas.create_line([(barrierX,yGap),(sliceX,sliceY)], width=1, fill='orange', dash=',')
      #draw text showing the distances
      yText = (yGap + sliceY)/2
      xText = (barrierX+sliceX)/2
      Ezcanvas.create_text(xText, yText, text=distStrVar.get(), fill="Cyan", font=("Helvetica", "12"))
      EzRMScanvas.create_text(xText, yText, text=distStrVar.get(), fill="Cyan", font=("Helvetica", "12"))
  
  #now, draw the horizontal slice
  lineID = Ezcanvas.create_line([(0,sliceY),(canvasX,sliceY)], width=1, fill='yellow', dash='-') 
  Ezcanvas.tag_bind(lineID, "<Button-1>",  horizClickMethod)
  lineID = EzRMScanvas.create_line([(0,sliceY),(canvasX,sliceY)], width=1, fill='green', dash='-')
  EzRMScanvas.tag_bind(lineID, "<Button-1>",  horizClickMethod)    
  lineID = VertPlotCanvas1.create_line([(0,sliceY),(plotD,sliceY)], width=1, fill='blue', dash='-')
  VertPlotCanvas1.tag_bind(lineID, "<Button-1>",  horizClickMethod)
  lineID = VertPlotCanvas2.create_line([(0,sliceY),(plotD,sliceY)], width=1, fill='blue', dash='-')
  VertPlotCanvas2.tag_bind(lineID, "<Button-1>",  horizClickMethod)    
    
  #the vertical slice
  lineID = Ezcanvas.create_line([(sliceX,0),(sliceX,canvasY)], width=1, fill='yellow', dash='-') 
  Ezcanvas.tag_bind(lineID, "<Button-1>",  vertClickMethod)
  lineID = EzRMScanvas.create_line([(sliceX,0),(sliceX,canvasY)], width=1, fill='green', dash='-')
  EzRMScanvas.tag_bind(lineID, "<Button-1>",  vertClickMethod)
  lineID = HorizPlotCanvas.create_line([(sliceX,0),(sliceX,plotD)], width=1, fill='blue', dash='-')
  HorizPlotCanvas.tag_bind(lineID, "<Button-1>",  vertClickMethod)
 
  #if we haven't reached steady state yet, display a countdown with the number of steps until stability on EzRMScanvas
  #this is drawn last so that it's on top of everything
  if n <= nCount:
    EzRMScanvas.create_text(canvasX/2,canvasY/2, text=str(nCount-n), fill="Red", font=("Helvetica", "75"))
  elif nAveraging < nAvgStable:
    EzRMScanvas.create_text(canvasX/2,canvasY/2, text=str(nAvgStable-nAveraging), fill="Magenta", font=("Helvetica", "75"))
 
  #finially, show the current information about the slice intersection point
  tStringVar.set("t=" + str(n) + "dt")

def conditionalRedraw():
  """In many cases, we want to redraw the canvas because something has changed. However, if it's running, the canvas will be redrawn soon anyway, so we don't need to do an extra redraw."""
  if not running and not fastForwarding:
    redrawCanvases()  
  
def horizClickMethod(eventObj):
  """Binds a method to the appropriate canvases so that we can change sliceY with the mouse"""
  Ezcanvas.bind('<B1-Motion>', lambda eventObj: setSliceY(eventObj.y))
  EzRMScanvas.bind('<B1-Motion>', lambda eventObj: setSliceY(eventObj.y))
  VertPlotCanvas1.bind('<B1-Motion>', lambda eventObj: setSliceY(eventObj.y))
  VertPlotCanvas2.bind('<B1-Motion>', lambda eventObj: setSliceY(eventObj.y))

def setSliceY(y):
  """Sets sliceY to the new value if appropriate"""
  global sliceY
  
  if (y >= 0) and (y < canvasY):
    sliceY = y
    yStringVar.set("y=" + str(sliceY) + "d")
    updateDistStrVars()
    conditionalRedraw()
    
def vertClickMethod(eventObj):
  """Binds a method to the appropriate canvases so that we can change sliceX with the mouse"""
  Ezcanvas.bind('<B1-Motion>', lambda eventObj: setSliceX(eventObj.x))
  EzRMScanvas.bind('<B1-Motion>', lambda eventObj: setSliceX(eventObj.x))
  HorizPlotCanvas.bind('<B1-Motion>', lambda eventObj: setSliceX(eventObj.x))

def setSliceX(x):
  """Sets sliceX to the new value if appropriate"""
  global sliceX
  
  if (x >= 0) and (x < canvasX):
    sliceX = x
    xStringVar.set("x=" + str(sliceX) + "d")
    updateDistStrVars()
    conditionalRedraw()  
    
def resetAveraging():
  """Reset averaged quantities and timers"""
  global nAveraging
  global EzSQsum
  global EzRMSSQ
  global EzRMS
  
  nAveraging = 0
  EzSQsum = zeros((canvasX, canvasY))
  EzRMSSQ = zeros((canvasX, canvasY))
  EzRMS = zeros((canvasX, canvasY))
  conditionalRedraw()
      
def reset():
  """Reset all field quantities and times"""
  global n
  global Ez
  global Ezx
  global Ezy
  global EzVis
  global Hx
  global Hy
  global t
  global maxEz
  global nCount
  global running
  
  running = False
  Hx = zeros((NHXx, NHXy))
  Hy = zeros((NHYx, NHYy))
  n = 0
  nCount = nStable
  Ez = zeros((NEZx, NEZy))
  Ezx = zeros((NEZx, NEZy))
  Ezy = zeros((NEZx, NEZy))
  EzVis = zeros((canvasX,canvasY))
  maxEz = 1.0
  resetAveraging() #contains a conditionalRedraw()
  
def start():
  """Starts the simulation if it's stopped"""
  global running
  
  if not running:
    running = True
    run()
    
def stop():
  """Stops the simulation"""
  global running

  running = False
  
def fastForward():
  """Starts fast forwarding the simulation"""
  global nCount
  global fastForwarding
  
  fastForwarding = True
  if nCount < n: #we've already reached stability, so now we're fast forwarding to get good averaging
    root.after(1,lambda: fastForwardStep(True))
  else: #we're fast forwarding to get Ez stability
    root.after(1,lambda: fastForwardStep(False))

    
def fastForwardStep(fastForwardWithAvg):
  """Runs the simulation for the appropriate time without displaying the results.
  If n<=nCount, then we're running until Ez is stable.
  If fastForwardWithAvg==True and nAveraging<nAvgStable, then we're running to get good averaging"""
  global ezPlot
  global fastForwarding

  #if n<=nCount, then Ez is unstable and we want to run until Ez is stable
  #if we're in fastForwardWithAvg mode, then we're running until EzRMS and EzRMSSQ are stable
  #so we run until nAveraging == nAvgStable
  if n <= nCount or (fastForwardWithAvg and nAveraging < nAvgStable):
    #clear canvases and display countdown
    Ezcanvas.delete('all')
    EzRMScanvas.delete('all')
    if fastForwardWithAvg:
      Ezcanvas.create_text(canvasX/2,canvasY/2, text=str(nAvgStable-nAveraging), fill="Magenta", font=("Helvetica", "75")) 
      EzRMScanvas.create_text(canvasX/2,canvasY/2, text=str(nAvgStable-nAveraging), fill="Magenta", font=("Helvetica", "75"))       
    else:
      Ezcanvas.create_text(canvasX/2,canvasY/2, text=str(nCount-n), fill="Red", font=("Helvetica", "75")) 
      EzRMScanvas.create_text(canvasX/2,canvasY/2, text=str(nCount-n), fill="Red", font=("Helvetica", "75")) 
    step(avg=fastForwardWithAvg) #only average if we're not going to reset right after we're done fast forwarding
    root.after(1,lambda: fastForwardStep(fastForwardWithAvg))
  else: #stop fast forwarding
    fastForwarding = False
    if not fastForwardWithAvg:
      resetAveraging()
    if running:
      run()
    else:
      start()

def singleStep():
  """Avances the simulation for one step, so long as the simulation is not running or fastforwarding"""
  if (not running) and (not fastForwarding):
    if n == nCount: #now that Ez is stable, reset the averaging so that it can reach stability
      resetAveraging()
    step()
    redrawCanvases()    
    
def run():
  """Runs the simulation while displaying the results at every step"""
  if running:
    timer = time.clock()
    if n == nCount: #now that Ez is stable, reset the averaging so that it can reach stability
      resetAveraging()
    step()
    redrawCanvases()
    print str(time.clock()-timer)
    if not fastForwarding:
      root.after(1,run)
  
def step(avg=True):
  """Advances the field quantities by one timestep"""
  global Ez
  global Ezx
  global Ezy
  global EzVis
  global EzAn
  global Hz
  global Hy
  global n
  global nAveraging
  global EzSQsum
  global EzRMSSQ
  global EzRMS
  global maxEzRMS
  global maxEz
  
  #take care of Hx and Hy using the standard Yee algorithm
  Hx[HXx_range, HXy_range] = DaY*Hx[HXx_range, HXy_range] + DbY*(Ez[HXx_range, HXy_range] - Ez[HXx_range, 1:(NHXy+1)]) #HXy_range+1
  Hy[HYx_range, HYy_range] = DaX*Hy[HYx_range, HYy_range] + DbX*(Ez[1:(NHYx+1), HYy_range] - Ez[HYx_range, HYy_range]) #HYx_range+1
    
  #do the normal Yee updates on Ez in the relevant range
  Ezx[EZx_range, EZy_range] = CaX*Ezx[EZx_range, EZy_range] + CbX*(Hy[EZx_range, EZy_range] - Hy[0:(NEZx-2),EZy_range])
  Ezy[EZx_range, EZy_range] = CaY*Ezy[EZx_range, EZy_range] + CbY*(Hx[EZx_range, 0:NEZy-2] - Hx[EZx_range, EZy_range])
    
  #Ez is the sum of the two split-field parts
  Ez = Ezx + Ezy
  
  #finially, update the time and the sources
  n += 1

  #next, update EzAn
  #x and y for points on and to the left of the barrier
  x, y = d * mgrid[EZx_an_range, EZy_an_range]
  
  #want wave to ramp up the wave's magnitude gradually and propogate at speed of light
  #logistic growth makes it come in gradually and use of retarded time there and in step function enforces propogation
  #to increase efficency, don't worry about either after t > (barrierX*d/c + 10*tau)
  #at that point, the wave will already have reached the barrier and grown to nearly full strength
  EzAn = sin(k*x-omega*n*dt)
  if n*dt < (barrierX*d/c + 10*tau):
    tr = n*dt - x/c
    EzAn *= ((tr > 0).astype(float))/(1+exp(-(tr-3*tau)/tau))
  
  #now, copy the right edge of EzAn to the overlapping part of Ez's left edge
  Ez[0,(pmlWidth+1):-(pmlWidth+1)] = EzAn[-1,:]
  
  #now, enforce Ez=0 on barrier
  invGaps = invertedGaps()
  for i in range(0,len(invGaps),2):
    Ez[0, invGaps[i]+pmlWidth+1:invGaps[i+1]+pmlWidth+1] = 0 #need to add PML and PEC offset since inverted gaps works on visible coordinate system    
  
  #now, stitch the two together to make the visible domain
  EzVis[EZx_an_range, :] = EzAn
  EzVis[barrierX:canvasX,:] = Ez[EZx_vis_range, EZy_vis_range] #overlaps with right edge of EzAn, so overwrites it 
   
  #first, only average if avg is true
  #2nd, stop averaging once we've got enough points (i.e. after nAveraging == nAvgStable)
  #however, if Ez still isn't stable (i.e. n < nCount) then keep averaging anyway
  if avg and (nAveraging < nAvgStable or n < nCount):
    nAveraging += 1
    EzSQsum += square(EzVis)
    
    EzRMSSQ = EzSQsum/nAveraging
    EzRMS   = EzRMSSQ
    
    maxEzRMS = max(EzRMS)
    if maxEzRMS == 0:
      maxEzRMS = 1 #avoid division by zero problems
    seterr(invalid='raise')
  #because Ez oscillates, it's maximum will change a little in time, so we store it and update it if we find something larger
  tempMaxEz = max(abs(EzVis))
  if tempMaxEz > maxEz:
    maxEz = tempMaxEz
      
#THE GUI-----------------------------------------------------------------------
#The root window
root = Tkinter.Tk()
root.title("Симуляция распространения волн")

#The menubar and menus
menubar = Tkinter.Menu(root)

#the file menu
filemenu = Tkinter.Menu(menubar, tearoff=0)
filemenu.add_command(label="Выйти", accelerator="Ctrl+Q", command=root.quit)
#bind keys to the actions
root.bind_all('<Control-q>', lambda arg: root.quit())
menubar.add_cascade(label="Файл", menu=filemenu)

traceSetting = Tkinter.StringVar(value="line")
avgSetting = Tkinter.StringVar(value='amp')
distLineSetting = Tkinter.StringVar(value="lines")

#the simulation me3u
simmenu = Tkinter.Menu(menubar, tearoff=0)
simmenu.add_command(label="Запуск", accelerator="Ctrl+R", command=start)
root.bind("<Control-r>", lambda arg: start())
simmenu.add_command(label="Стоп", accelerator="Ctrl+S", command=stop)
root.bind("<Control-s>", lambda arg: stop())
simmenu.add_command(label="Один шаг", accelerator="Ctrl+T", command=stop)
root.bind("<Control-t>", lambda arg: singleStep())
simmenu.add_command(label="Перезагрузить", accelerator="Ctrl+Shift+R", command=reset)
root.bind("<Control-R>", lambda arg: reset())
simmenu.add_command(label="Пересчитать среднее", accelerator="Ctrl+Shift+A", command=resetAveraging)
root.bind("<Shift-A>", lambda arg: resetAveraging())
simmenu.add_command(label="Ускорить", accelerator="Ctrl+F", command=fastForward)
root.bind("<Control-f>", lambda arg: fastForward())
menubar.add_cascade(label="Симуляция", menu=simmenu)

root.config(menu=menubar)

#The view frame
viewFrame = ttk.Labelframe(root, text='Вид')
viewFrame.grid(column=0, row=0, sticky='nsew',padx=5,pady=5)

Ezcanvas = Tkinter.Canvas(viewFrame, width=canvasX, height=canvasY)
Ezcanvas.grid(column=3, row=0, columnspan=3, rowspan=3, sticky='nsew', padx=5, pady=5)    

HorizPlotCanvas = Tkinter.Canvas(viewFrame, width=canvasX, height=plotD)
HorizPlotCanvas.grid(column=3, row=3, columnspan=3, rowspan=5, sticky='nsew', padx=5, pady=5)

sliceY = 60 #position of horizontal slice
sliceX = canvasX/2

xStringVar = Tkinter.StringVar(value="x=" + str(sliceX) + "d")
yStringVar = Tkinter.StringVar(value="y=" + str(sliceY) + "d")
tStringVar = Tkinter.StringVar()
EzStringVar = Tkinter.StringVar()
EzRMSStringVar = Tkinter.StringVar()
ttk.Label(viewFrame, textvariable=xStringVar).grid(column=0, row=3, sticky='nsew', padx=5, pady=0)
ttk.Label(viewFrame, textvariable=yStringVar).grid(column=0, row=4, sticky='nsew', padx=5, pady=0)
ttk.Label(viewFrame, textvariable=tStringVar).grid(column=0, row=5, sticky='nsew', padx=5, pady=0)    
ttk.Label(viewFrame, textvariable=EzStringVar).grid(column=0, row=6, sticky='nsew', padx=5, pady=0)    
ttk.Label(viewFrame, textvariable=EzRMSStringVar).grid(column=0, row=7, sticky='nsew', padx=5, pady=0)    

VertPlotCanvas1 = Tkinter.Canvas(viewFrame, width=plotD, height=canvasY)
VertPlotCanvas1.grid(column=0, row=0, columnspan=1, rowspan=3, sticky='nsew', padx=5, pady=5)
VertPlotCanvas2 = Tkinter.Canvas(viewFrame, width=plotD, height=canvasY)
VertPlotCanvas2.grid(column=0, row=8, columnspan=1, rowspan=3, sticky='nsew', padx=5, pady=5)

EzRMScanvas = Tkinter.Canvas(viewFrame, width=canvasX, height=canvasY)
EzRMScanvas.grid(column=3, row=8, columnspan=3, rowspan=3, sticky='nsew', padx=5, pady=5)

#make it so that, after dragging an element has ceased, the binding is reset so that further dragging won't move the element unless it gets clicked again first
#we do this by binding to any motion on any canvas
Ezcanvas.bind("<Motion>", clearCanvasBindings)
HorizPlotCanvas.bind("<Motion>", clearCanvasBindings)
EzRMScanvas.bind("<Motion>", clearCanvasBindings)
VertPlotCanvas1.bind("<Motion>", clearCanvasBindings)
VertPlotCanvas2.bind("<Motion>", clearCanvasBindings)

#make the arrow keys control the slice positions
root.bind_all("<Up>", lambda arg: setSliceY(sliceY-1))
root.bind_all("<Down>", lambda arg: setSliceY(sliceY+1))
root.bind_all("<Right>", lambda arg: setSliceX(sliceX+1))
root.bind_all("<Left>", lambda arg: setSliceX(sliceX-1))

#The barrier frame and intial barrier setup
barrierFrame = ttk.Labelframe(root, text='Барьер')
barrierFrame.grid(column=1,row=0,sticky='nsew',padx=5,pady=5)

ttk.Button(barrierFrame, text='Добавить отверстие', command=addOpening).grid(column=0, row=0, columnspan=2, sticky='nsew', padx=5, pady=5)
ttk.Label(barrierFrame, text="Нижнее значение:").grid(column=0, row=1, sticky='nes', padx=5, pady=5)
bottomEntry = Tkinter.Spinbox(barrierFrame, width=4, from_=0, to=canvasX)
bottomEntry.bind("<Return>",lambda arg: root.focus()) #removes focus after the number is entered
bottomEntry.grid(column=1, row=1, sticky='nsw', padx=5, pady=5)
ttk.Label(barrierFrame, text="Верхнее значение:").grid(column=0, row=2, sticky='nes', padx=5, pady=5)
topEntry = Tkinter.Spinbox(barrierFrame, width=4, from_=0, to=canvasX)
topEntry.bind("<Return>",lambda arg: root.focus()) #removes focus after the number is entered
topEntry.grid(column=1, row=2, sticky='nsw', padx=5, pady=5)

gaps = [[40,100],[180,240]] #good for standard double slit experiment
barrierFrames = [] #stores the frames for each opening in the barrier; need to initialize it as an empty array

#draw on the canvases and set up the barrier frame
redrawBarrierFrame()
redrawCanvases()

#set everything in motion
root.mainloop()
